# scenario_cov.py
import os
import json
import yaml
import pytest
from pathlib import Path
from typing import Dict, Set, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ScenarioInfo:
    """Информация о сценарии"""
    id: str
    desc: str
    category: str = ""
    priority: str = "normal"  # low, normal, high, critical

    @property
    def category_from_id(self) -> str:
        """Автоматически определяет категорию по ID (S1 -> S1, S2 -> S2, etc.)"""
        if not self.category and '.' in self.id:
            return self.id.split('.')[0]
        return self.category or "unknown"


@dataclass
class CoverageReport:
    """Отчёт о покрытии"""
    total_scenarios: int
    covered_scenarios: int
    missing_scenarios: List[ScenarioInfo]
    coverage_percentage: float
    test_run_time: str
    categories_stats: Dict[str, Dict[str, int]]


class ScenarioTracker:
    def __init__(self):
        self.expected: Dict[str, ScenarioInfo] = {}
        self.covered: Set[str] = set()
        self.node_to_ids: Dict[str, List[str]] = {}
        self.failed_tests: Set[str] = set()

    def load_scenarios(self, config_path: Path) -> None:
        """Загружает сценарии из YAML файла"""
        if not config_path.exists():
            return

        try:
            data = yaml.safe_load(config_path.read_text()) or []
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    scenario = ScenarioInfo(
                        id=item["id"],
                        desc=item.get("desc", ""),
                        category=item.get("category", ""),
                        priority=item.get("priority", "normal")
                    )
                    self.expected[scenario.id] = scenario
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse scenarios.yml: {e}")

    def register_test(self, nodeid: str, scenario_ids: List[str]) -> None:
        """Регистрирует тест и его сценарии"""
        # Проверяем, что все ID существуют
        invalid_ids = [sid for sid in scenario_ids if sid not in self.expected]
        if invalid_ids:
            print(f"Warning: Test {nodeid} references unknown scenarios: {invalid_ids}")

        self.node_to_ids[nodeid] = scenario_ids

    def mark_covered(self, nodeid: str, passed: bool) -> None:
        """Отмечает сценарии как покрытые, если тест прошёл"""
        if passed:
            for sid in self.node_to_ids.get(nodeid, []):
                if sid in self.expected:
                    self.covered.add(sid)
        else:
            self.failed_tests.add(nodeid)

    def get_missing_scenarios(self) -> List[ScenarioInfo]:
        """Возвращает список непокрытых сценариев"""
        missing_ids = set(self.expected.keys()) - self.covered
        return [self.expected[sid] for sid in sorted(missing_ids)]

    def get_coverage_percentage(self) -> float:
        """Вычисляет процент покрытия"""
        if not self.expected:
            return 100.0
        return (len(self.covered) / len(self.expected)) * 100

    def get_categories_stats(self) -> Dict[str, Dict[str, int]]:
        """Статистика по категориям"""
        stats = {}

        # Группируем все сценарии по категориям
        all_by_category = {}
        for scenario in self.expected.values():
            cat = scenario.category_from_id
            if cat not in all_by_category:
                all_by_category[cat] = []
            all_by_category[cat].append(scenario)

        # Считаем покрытие по категориям
        for category, scenarios in all_by_category.items():
            total = len(scenarios)
            covered = len([s for s in scenarios if s.id in self.covered])
            missing = total - covered
            percentage = (covered / total * 100) if total > 0 else 0

            stats[category] = {
                "total": total,
                "covered": covered,
                "missing": missing,
                "percentage": round(percentage, 1)
            }

        return stats

    def generate_report(self) -> CoverageReport:
        """Генерирует полный отчёт о покрытии"""
        missing = self.get_missing_scenarios()

        return CoverageReport(
            total_scenarios=len(self.expected),
            covered_scenarios=len(self.covered),
            missing_scenarios=missing,
            coverage_percentage=round(self.get_coverage_percentage(), 1),
            test_run_time=datetime.now().isoformat(),
            categories_stats=self.get_categories_stats()
        )

    def save_report_json(self, path: Path, report: CoverageReport) -> None:
        """Сохраняет отчёт в JSON"""
        try:
            # Конвертируем ScenarioInfo в dict для JSON
            report_dict = asdict(report)
            report_dict["missing_scenarios"] = [
                asdict(scenario) for scenario in report.missing_scenarios
            ]

            path.write_text(json.dumps(report_dict, indent=2, ensure_ascii=False))
            print(f"[scenario coverage] Отчёт сохранён: {path}")
        except Exception as e:
            print(f"Warning: Failed to save JSON report: {e}")


# Глобальный трекер
_tracker = ScenarioTracker()


def covers(*scenario_ids: str):
    """Декоратор: @covers('S1.1','S1.2') помечает тест покрывающим сценарии."""
    return pytest.mark.covers(*scenario_ids)


def pytest_addoption(parser):
    parser.addoption("--scenario-enforce", action="store_true",
                     help="Падать, если остались непокрытые сценарии")
    parser.addoption("--scenario-report-json", type=str,
                     help="Путь для сохранения JSON отчёта")
    parser.addoption("--scenario-min-coverage", type=float, default=0.0,
                     help="Минимальный процент покрытия (по умолчанию 0)")


def pytest_configure(config):
    """Настройка pytest плагина"""
    # Загружаем сценарии (основные + ботовские)
    base = Path(config.rootpath, "tests")
    candidates = [

        #base / "payment" /"scenarios.yml",
        #base / "bot" / "scenarios.yml",
        base / "bot_admin_merchant" /"scenarios.yml",
    ]
    for p in candidates:
        _tracker.load_scenarios(p)

    # Регистрируем маркер
    config.addinivalue_line(
        "markers",
        "covers(*ids): пометить тест покрывающим сценарий(и)"
    )



def pytest_collection_modifyitems(items):
    """Собираем информацию о тестах и их сценариях"""
    for item in items:
        scenario_ids = []
        for marker in item.iter_markers(name="covers"):
            scenario_ids.extend(list(marker.args))

        if scenario_ids:
            _tracker.register_test(item.nodeid, scenario_ids)


def pytest_runtest_logreport(report):
    """Отслеживаем результаты тестов"""
    if report.when == "call":
        _tracker.mark_covered(report.nodeid, report.passed)


def pytest_sessionfinish(session, exitstatus):
    """Финальная обработка и вывод отчёта"""
    config = session.config
    enforce = config.getoption("--scenario-enforce")
    json_path = config.getoption("--scenario-report-json")
    min_coverage = config.getoption("--scenario-min-coverage")

    # Генерируем отчёт
    report = _tracker.generate_report()

    # Сохраняем JSON отчёт если нужно
    if json_path:
        _tracker.save_report_json(Path(json_path), report)

    # Выводим результаты
    _print_coverage_report(report)

    # Проверяем условия для фейла
    should_fail = False

    if report.missing_scenarios and enforce:
        print(f"\n❌ --scenario-enforce: Есть непокрытые сценарии!")
        should_fail = True

    if report.coverage_percentage < min_coverage:
        print(f"\n❌ Покрытие {report.coverage_percentage}% меньше требуемых {min_coverage}%")
        should_fail = True

    if should_fail:
        session.exitstatus = 2


def _print_coverage_report(report: CoverageReport) -> None:
    """Выводит отчёт в консоль"""
    print("\n" + "=" * 60)
    print("📊 ОТЧЁТ О ПОКРЫТИИ СЦЕНАРИЕВ")
    print("=" * 60)

    # Общая статистика
    emoji = "✅" if report.coverage_percentage == 100 else "⚠️" if report.coverage_percentage >= 80 else "❌"
    print(f"{emoji} Покрытие: {report.covered_scenarios}/{report.total_scenarios} ({report.coverage_percentage}%)")

    # Статистика по категориям
    if report.categories_stats:
        print("\n📂 По категориям:")
        for category, stats in sorted(report.categories_stats.items()):
            emoji = "✅" if stats["percentage"] == 100 else "⚠️" if stats["percentage"] >= 80 else "❌"
            print(f"  {emoji} {category}: {stats['covered']}/{stats['total']} ({stats['percentage']}%)")

    # Непокрытые сценарии
    if report.missing_scenarios:
        print(f"\n❌ Непокрытые сценарии ({len(report.missing_scenarios)}):")

        # Группируем по категориям для лучшего отображения
        by_category = {}
        for scenario in report.missing_scenarios:
            cat = scenario.category_from_id
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(scenario)

        for category in sorted(by_category.keys()):
            print(f"\n  📁 {category}:")
            for scenario in by_category[category]:
                priority_emoji = {"critical": "🔥", "high": "⚠️", "normal": "📋", "low": "📝"}.get(scenario.priority, "📋")
                print(f"    {priority_emoji} {scenario.id}: {scenario.desc}")

    else:
        print("\n✅ Все сценарии покрыты!")

    # Информация о неудачных тестах
    if _tracker.failed_tests:
        print(f"\n⚠️  Неудачные тесты ({len(_tracker.failed_tests)}):")
        for nodeid in sorted(_tracker.failed_tests):
            scenarios = _tracker.node_to_ids.get(nodeid, [])
            scenarios_str = ", ".join(scenarios) if scenarios else "без сценариев"
            print(f"    ❌ {nodeid} ({scenarios_str})")

    print("=" * 60)