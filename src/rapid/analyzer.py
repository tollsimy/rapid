import json
import sys
import os
import sqlite3
from collections import defaultdict
from prettytable import PrettyTable
from typing import Dict, Any, List


class ResultsAnalyzer:
    STATUS_COLORS = {
        'passed': '#2ecc71',     # Green
        'failed': '#e74c3c',     # Red
        'halt': '#f39c12',    # Orange
        'trap': '#9b59b6',       # Purple
        'outlier': '#3498db',    # Blue
        'SDC': '#e67e22',  # Dark Orange
        'hw-reset': '#c0392b',   # Dark Red
        'comm_failure': '#34495e',  # Navy
        'missing': '#95a5a6',    # Gray
        'unknown': '#7f8c8d'     # Dark Gray
    }
    
    SUBCAT_COLORS = {
        "clean": "#a9dfbf",       # Light green
        "trap": "#9b59b6",   # Purple
        "SDC": "#e67e22", # Orange
        "halt": "#f39c12",     # Yellow-orange
        "comm_failure": "#34495e",   # Navy
        "other": "#95a5a6",       # Gray
        "all": "#85c1e9"          # Light blue
    }
    
    LINE_STYLES = {
        'passed': '-',
        'failed': '--',
        'trap': '-.',
        'halt': ':'
    }
    
    def __init__(self, db_path: str, benchmark: str = None):
        """Initialize analyzer with database path and optional benchmark name"""
        self.db_path = db_path
        self.conn = self._connect_db()
        self.benchmark_name = benchmark
    
    def _connect_db(self) -> sqlite3.Connection:
        """Connect to the SQLite database"""
        if not os.path.exists(self.db_path):
            print(f"Error: Database not found at {self.db_path}")
            sys.exit(1)
            
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except sqlite3.Error as e:
            print(f"Error connecting to database: {e}")
            sys.exit(1)
    
    def _execute_query(self, query: str, params=None):
        """Execute a query and return results"""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    
    def get_available_benchmarks(self) -> List[str]:
        """Get a list of available benchmarks in the database"""
        cursor = self._execute_query("SELECT DISTINCT benchmark FROM tests")
        return [row[0] for row in cursor.fetchall()]
    
    def set_benchmark(self, benchmark: str):
        """Set the current benchmark for analysis"""
        self.benchmark_name = benchmark
    
    def _check_benchmark(self):
        """Verify benchmark is set"""
        if not self.benchmark_name:
            print("No benchmark selected")
            return False
        return True
    
    def count_by_status(self) -> Dict[str, int]:
        """Count tests by their status flags"""
        if not self._check_benchmark():
            return {}
            
        status_counts = {
            "passed": 0, "failed": 0, "trap": 0, "halt": 0, "outlier": 0,
            "SDC": 0, "hw-reset": 0, "comm_failure": 0, "exec_failure": 0
        }
        
        cursor = self._execute_query(
            "SELECT COUNT(*) FROM tests WHERE benchmark = ?", 
            (self.benchmark_name,)
        )
        total = cursor.fetchone()[0]
        
        cursor = self._execute_query(
            "SELECT class, COUNT(*) FROM status JOIN tests ON status.test_id = tests.test_id " +
            "WHERE tests.benchmark = ? GROUP BY class",
            (self.benchmark_name,)
        )
        for status, count in cursor.fetchall():
            if status in status_counts:
                status_counts[status] = count
        
        # Count various event types
        event_queries = {
            "SDC": "SELECT COUNT(*) FROM status JOIN tests ON status.test_id = tests.test_id WHERE tests.benchmark = ? AND SDC = 1",
            "trap": "SELECT COUNT(*) FROM traps JOIN tests ON traps.test_id = tests.test_id WHERE tests.benchmark = ?",
            "halt": "SELECT COUNT(*) FROM halts JOIN tests ON halts.test_id = tests.test_id WHERE tests.benchmark = ?",
            "hw-reset": "SELECT COUNT(*) FROM hw_resets JOIN tests ON hw_resets.test_id = tests.test_id WHERE tests.benchmark = ?",
            "comm_failure": "SELECT COUNT(*) FROM comm_failure JOIN tests ON comm_failure.test_id = tests.test_id WHERE tests.benchmark = ?",
            "exec_failure": "SELECT COUNT(*) FROM exec_failure JOIN tests ON exec_failure.test_id = tests.test_id WHERE tests.benchmark = ?"
        }
        
        for event, query in event_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            status_counts[event] = cursor.fetchone()[0]
        
        status_counts["total"] = total
        return status_counts
    
    def count_by_trap_cause(self) -> Dict[str, int]:
        """Analyze trap causes and return their descriptive names with counts"""
        if not self._check_benchmark():
            return {}
            
        cursor = self._execute_query(
            "SELECT scause, COUNT(*) FROM traps " +
            "JOIN tests ON traps.test_id = tests.test_id " +
            "WHERE tests.benchmark = ? GROUP BY scause",
            (self.benchmark_name,)
        )
        
        raw_results = cursor.fetchall()
        named_results = {}
        for cause_num, count in raw_results:
            cause_name = self.convert_trap_cause_to_name(cause_num)
            named_results[cause_name] = count
        
        return named_results
    
    def convert_trap_cause_to_name(self, cause: int) -> str:
        """Convert numerical trap cause to descriptive name."""
        if isinstance(cause, str):
            try:
                if cause.lower().startswith('0x'):
                    cause = int(cause, 16)
                else:
                    cause = int(cause)
            except ValueError:
                return f"Reserved ({cause})"
        
        # u74mc sepc
        causes = {
            0x0: "Instruction address misaligned",
            0x1: "Instruction access fault",
            0x2: "Illegal instruction",
            0x3: "Breakpoint",
            0x4: "Reserved (0x4)",
            0x5: "Load access fault",
            0x6: "Store/AMO address misaligned",
            0x7: "Store/AMO access fault",
            0x8: "Environment call from U-mode",
            0x9: "Reserved (0x9)",
            0xA: "Reserved (0xA)",
            0xB: "Reserved (0xB)",
            0xC: "Instruction page fault",
            0xD: "Load page fault",
            0xE: "Reserved (0xE)",
            0xF: "Store/AMO page fault"
        }
        
        return causes.get(cause, f"Reserved ({hex(cause) if isinstance(cause, int) else cause})")
    
    def analyze_test_coverage(self) -> Dict[str, int]:
        """Analyze test coverage statistics"""
        if not self._check_benchmark():
            return {}
            
        query_templates = [
            ("total_tests", "SELECT COUNT(*) FROM tests WHERE benchmark = ?"),
            ("with_output", "SELECT COUNT(*) FROM tests WHERE benchmark = ? AND output IS NOT NULL"),
            ("needs_manual_check", "SELECT COUNT(*) FROM tests WHERE benchmark = ? AND needs_manual_check = 1")
        ]
        
        result = {}
        for key, query in query_templates:
            cursor = self._execute_query(query, (self.benchmark_name,))
            result[key] = cursor.fetchone()[0]
            
        return result
    
    def analyze_by_bit_position(self) -> Dict[str, Dict[int, int]]:
        """Analyze results by bit position"""
        if not self._check_benchmark():
            return {}
            
        bit_position_stats = {
            "passed": defaultdict(int),
            "failed": defaultdict(int),
            "trap": defaultdict(int),
            "halt": defaultdict(int)
        }
        
        query_templates = {
            "passed": "SELECT t.bit_position, COUNT(*) FROM tests t " +
                    "JOIN status s ON t.test_id = s.test_id " +
                    "WHERE t.benchmark = ? AND s.class = 'passed' AND t.bit_position IS NOT NULL " +
                    "GROUP BY t.bit_position",
                    
            "failed": "SELECT t.bit_position, COUNT(*) FROM tests t " +
                    "JOIN status s ON t.test_id = s.test_id " +
                    "WHERE t.benchmark = ? AND s.class = 'failed' AND t.bit_position IS NOT NULL " +
                    "GROUP BY t.bit_position",
                    
            "trap": "SELECT t.bit_position, COUNT(*) FROM tests t " +
                    "JOIN traps tr ON t.test_id = tr.test_id " +
                    "WHERE t.benchmark = ? AND t.bit_position IS NOT NULL " +
                    "GROUP BY t.bit_position",
                    
            "halt": "SELECT t.bit_position, COUNT(*) FROM tests t " +
                    "JOIN halts tout ON t.test_id = tout.test_id " +
                    "WHERE t.benchmark = ? AND t.bit_position IS NOT NULL " +
                    "GROUP BY t.bit_position"
        }
        
        for status_type, query in query_templates.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            for bit_pos, count in cursor.fetchall():
                bit_position_stats[status_type][bit_pos] = count
        
        return bit_position_stats
    
    def get_status_hierarchy_counts(self) -> Dict[str, Dict[str, int]]:
        """Get hierarchical status counts"""
        if not self._check_benchmark():
            return {}
            
        counts = {
            "passed": {"clean": 0, "trap": 0, "SDC": 0, "halt": 0, "comm_failure": 0, "total": 0},
            "failed": {"clean": 0, "trap": 0, "SDC": 0, "halt": 0, "comm_failure": 0, "exec_failure": 0, "total": 0},
            "outlier": {"trap": 0, "SDC": 0, "halt": 0, "comm_failure": 0, "total": 0}
        }
        
        self._get_basic_status_counts(counts)
        self._get_event_counts_by_status(counts)
        self._get_special_cases(counts)
        
        return counts

    def _get_basic_status_counts(self, counts):
        """Get the total count for each main status category"""
        categories = ["passed", "failed", "outlier"]
        
        for category in categories:
            cursor = self._execute_query(
                "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id " +
                "WHERE t.benchmark = ? AND s.class = ?",
                (self.benchmark_name, category)
            )
            counts[category]["total"] = cursor.fetchone()[0]

    def _get_event_counts_by_status(self, counts):
        """Get counts of various events within each status category"""
        events = ["trap", "halt", "comm_failure"]
        categories = ["passed", "failed", "outlier"]
        event_queries = {
            "trap": "JOIN traps tr ON t.test_id = tr.test_id",
            "halt": "JOIN halts h ON t.test_id = h.test_id",
            "comm_failure": "JOIN comm_failure c ON t.test_id = c.test_id"
        }
        
        for category in categories:
            for event in events:
                query = (
                    f"SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id " +
                    f"{event_queries[event]} " +
                    f"WHERE t.benchmark = ? AND s.class = ?"
                )
                cursor = self._execute_query(query, (self.benchmark_name, category))
                counts[category][event] = cursor.fetchone()[0]
        
        for category in categories:
            cursor = self._execute_query(
                "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id " +
                f"WHERE t.benchmark = ? AND s.class = ? AND s.SDC = 1",
                (self.benchmark_name, category)
            )
            counts[category]["SDC"] = cursor.fetchone()[0]
        
        cursor = self._execute_query(
            "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id " +
            "JOIN exec_failure e ON t.test_id = e.test_id " +
            "WHERE t.benchmark = ? AND s.class = 'failed'",
            (self.benchmark_name,)
        )
        counts["failed"]["exec_failure"] = cursor.fetchone()[0]

    def _get_special_cases(self, counts):
        """Get counts for special cases like clean passes"""
        # Clean passes - passed tests with no issues
        cursor = self._execute_query('''
            SELECT COUNT(*) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN hw_resets hr ON t.test_id = hr.test_id
            WHERE t.benchmark = ? AND s.class = 'passed' AND s.SDC = 0
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND hr.test_id IS NULL
        ''', (self.benchmark_name,))
        counts["passed"]["clean"] = cursor.fetchone()[0]
        
        # Clean failures - failed tests with no specific cause identified
        cursor = self._execute_query('''
            SELECT COUNT(*) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN hw_resets hr ON t.test_id = hr.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND s.class = 'failed'
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND hr.test_id IS NULL
            AND e.test_id IS NULL
        ''', (self.benchmark_name,))
        counts["failed"]["clean"] = cursor.fetchone()[0]
        
    def find_tests_with_status(self, status_name: str) -> List[str]:
        """Find all tests with a specific status"""
        if not self._check_benchmark():
            return []
            
        # Query template mapping
        query_mapping = {
            "trap": "SELECT t.test_id FROM tests t JOIN traps tr ON t.test_id = tr.test_id WHERE t.benchmark = ?",
            "halt": "SELECT t.test_id FROM tests t JOIN halts tout ON t.test_id = tout.test_id WHERE t.benchmark = ?",
            "hw-reset": "SELECT t.test_id FROM tests t JOIN hw_resets hr ON t.test_id = hr.test_id WHERE t.benchmark = ?",
            "hw_reset": "SELECT t.test_id FROM tests t JOIN hw_resets hr ON t.test_id = hr.test_id WHERE t.benchmark = ?",
            "comm_failure": "SELECT t.test_id FROM tests t JOIN comm_failure c ON t.test_id = c.test_id WHERE t.benchmark = ?",
            "SDC": "SELECT test_id FROM tests WHERE benchmark = ? AND SDC = 1",
        }
        
        if status_name in query_mapping:
            cursor = self._execute_query(query_mapping[status_name], (self.benchmark_name,))
        else:
            # Default for regular status values (passed, failed, outlier)
            cursor = self._execute_query(
                "SELECT t.test_id FROM tests t JOIN status s ON t.test_id = s.test_id " +
                "WHERE t.benchmark = ? AND s.type = ?",
                (self.benchmark_name, status_name)
            )
            
        return [row[0] for row in cursor.fetchall()]
    
    def print_summary(self):
        """Print summary of results with detailed hierarchical tables"""
        if not self._check_benchmark():
            return
            
        status_counts = self.count_by_status()
        coverage = self.analyze_test_coverage()
        counts = self.get_status_hierarchy_counts()
        total_tests = coverage["total_tests"]
        
        self.print_status_verification_table()
        self._print_strict_failures_table(counts, total_tests)
        self.print_trap_table(self.count_by_trap_cause())

    def print_trap_table(self, trap_causes):
        """Print trap causes table"""
        if not trap_causes:
            return
            
        table = PrettyTable()
        table.field_names = ["Trap Cause", "Count", "% of Traps"]
        table.align = "l"
        
        total_traps = sum(trap_causes.values())
        
        for cause, count in sorted(trap_causes.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_traps) * 100 if total_traps > 0 else 0
            table.add_row([cause, count, f"{pct:.2f}%"])
        
        table.add_row(["TOTAL TRAPS", total_traps, "100.00%"])
        
        print("\nTrap Causes Breakdown:")
        print(table)

    def _print_strict_failures_table(self, counts, total_tests):
        """Print a breakdown of strict failures by category"""
        # Get clean passed tests (true successes)
        clean_passed = counts["passed"]["clean"]
        
        # 1. Tests with exactly ONE trap (and nothing else), excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND h.test_id IS NULL
            AND c.test_id IS NULL AND e.test_id IS NULL AND s.SDC = 0
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        failed_with_trap = cursor.fetchone()[0]
        
        # 2. Tests with exactly ONE halt (and nothing else), excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND tr.test_id IS NULL
            AND c.test_id IS NULL AND e.test_id IS NULL AND s.SDC = 0
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        failed_halt = cursor.fetchone()[0]
        
        # 3. Tests with exactly ONE comm failure (and nothing else), excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND tr.test_id IS NULL
            AND h.test_id IS NULL AND e.test_id IS NULL AND s.SDC = 0
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        failed_comm_failure = cursor.fetchone()[0]
        
        # 4. Tests with exactly SDC (and nothing else), excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND s.SDC = 1 
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND e.test_id IS NULL
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        wrong_results = cursor.fetchone()[0]
        
        # 5. Tests with exactly execution failures (and nothing else), excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN exec_failure e ON t.test_id = e.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND tr.test_id IS NULL
            AND h.test_id IS NULL AND c.test_id IS NULL AND s.SDC = 0
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        exec_failure = cursor.fetchone()[0]
        
        # 6. Tests with multiple events - these go into "others", excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND t.needs_manual_check = 0 AND (
                (EXISTS(SELECT 1 FROM traps tr WHERE tr.test_id = t.test_id) + 
                EXISTS(SELECT 1 FROM halts h WHERE h.test_id = t.test_id) + 
                EXISTS(SELECT 1 FROM comm_failure c WHERE c.test_id = t.test_id) +
                EXISTS(SELECT 1 FROM exec_failure e WHERE e.test_id = t.test_id) +
                (s.SDC = 1)) > 1
            )
        ''', (self.benchmark_name,))
        multiple_events = cursor.fetchone()[0]
        
        # 7. Tests with 'failed' or 'outlier' status but no specific events, excluding manual checks
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND (s.class = 'failed' OR s.class = 'outlier')
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND e.test_id IS NULL AND s.SDC = 0
            AND t.needs_manual_check = 0
        ''', (self.benchmark_name,))
        no_events_failed = cursor.fetchone()[0]
        
        # 8. Uncategorized tests (manual check needed)
        cursor = self._execute_query('''
            SELECT COUNT(DISTINCT t.test_id) FROM tests t
            WHERE t.benchmark = ? AND t.needs_manual_check = 1
        ''', (self.benchmark_name,))
        uncategorized = cursor.fetchone()[0]
        
        others = multiple_events + no_events_failed
        
        total_failed = total_tests - clean_passed
        
        sum_of_categories = failed_with_trap + failed_halt + failed_comm_failure + wrong_results + exec_failure + others + uncategorized
        if sum_of_categories != total_failed:
            print(f"\nWARNING: Category sum ({sum_of_categories}) does not match total failures ({total_failed})")
            print(f"This suggests there might be an issue with the categorization logic.")
        
        trap_pct = (failed_with_trap / total_tests) * 100 if total_tests > 0 else 0
        halt_pct = (failed_halt / total_tests) * 100 if total_tests > 0 else 0
        comm_failure_pct = (failed_comm_failure / total_tests) * 100 if total_tests > 0 else 0
        sdc_pct = (wrong_results / total_tests) * 100 if total_tests > 0 else 0
        exec_failure_pct = (exec_failure / total_tests) * 100 if total_tests > 0 else 0
        others_pct = (others / total_tests) * 100 if total_tests > 0 else 0
        uncategorized_pct = (uncategorized / total_tests) * 100 if total_tests > 0 else 0
        total_failure_pct = (total_failed / total_tests) * 100 if total_tests > 0 else 0
        
        table = PrettyTable()
        table.field_names = ["Benchmark", "trap", "halt", "comm failure", "SDC", "exec failure", "others", "uncategorized", "Total"]
        table.align = "l"
        
        # Add row for percentages
        table.add_row([
            self.benchmark_name,
            f"{trap_pct:.2f}%",
            f"{halt_pct:.2f}%",
            f"{comm_failure_pct:.2f}%",
            f"{sdc_pct:.2f}%",
            f"{exec_failure_pct:.2f}%", 
            f"{others_pct:.2f}%",
            f"{uncategorized_pct:.2f}%",
            f"{total_failure_pct:.2f}%"
        ])
        
        table.add_row([
            "counts",
            str(failed_with_trap),
            str(failed_halt),
            str(failed_comm_failure),
            str(wrong_results),
            str(exec_failure),
            str(others),
            str(uncategorized),
            str(total_failed)
        ])
        
        print("\nStrict Failures Breakdown:")
        print(table)
        print("\nNote: Strict failures are tests that have reported events. A passed test with an event is considered a failure. An outlier is always a failed test.")
        print("\nNote: Main categories contain tests with EXACTLY that issue and no other events.")
        print("      'Others' includes tests with multiple events or no specific event.")
        print("      'Uncategorized' contains tests that need manual verification.")
        print(f"      Multiple events: {multiple_events}, No specific events: {no_events_failed}, Manual check needed: {uncategorized}")
        
    def print_status_verification_table(self):
        """Print detailed verification tables to check status calculation accuracy"""
        if not self._check_benchmark():
            return
            
        # Get raw counts directly from database for verification
        raw_counts = {}
        cursor = self._execute_query("SELECT COUNT(*) FROM tests WHERE benchmark = ?", (self.benchmark_name,))
        raw_counts["total_tests"] = cursor.fetchone()[0]
        cursor = self._execute_query(
            "SELECT COUNT(*) FROM tests WHERE benchmark = ? AND needs_manual_check = 1", 
            (self.benchmark_name,)
        )
        raw_counts["needs_manual_check"] = cursor.fetchone()[0]
        status_queries = {
            "passed": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "failed": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "outlier": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'outlier'"
        }
        event_queries = {
            "with_trap": "SELECT COUNT(*) FROM traps JOIN tests ON traps.test_id = tests.test_id WHERE tests.benchmark = ?",
            "halt": "SELECT COUNT(*) FROM halts JOIN tests ON halts.test_id = tests.test_id WHERE tests.benchmark = ?",
            "comm_failure": "SELECT COUNT(*) FROM comm_failure JOIN tests ON comm_failure.test_id = tests.test_id WHERE tests.benchmark = ?",
            "SDC": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.SDC = 1",
            "exec_failure": "SELECT COUNT(*) FROM exec_failure JOIN tests ON exec_failure.test_id = tests.test_id WHERE tests.benchmark = ?",
            "hw_reset": "SELECT COUNT(*) FROM hw_resets JOIN tests ON hw_resets.test_id = tests.test_id WHERE tests.benchmark = ?"
        }
        combined_queries = {
            "passed_with_trap": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN traps tr ON t.test_id = tr.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "passed_halt": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN halts h ON t.test_id = h.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "passed_comm_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN comm_failure c ON t.test_id = c.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "passed_SDC": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'passed' AND s.SDC = 1",
            "passed_exec_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN exec_failure e ON t.test_id = e.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "passed_hw_reset": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN hw_resets hr ON t.test_id = hr.test_id WHERE t.benchmark = ? AND s.class = 'passed'",
            "failed_with_trap": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN traps tr ON t.test_id = tr.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "failed_halt": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN halts h ON t.test_id = h.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "failed_comm_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN comm_failure c ON t.test_id = c.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "failed_SDC": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'failed' AND s.SDC = 1",
            "failed_exec_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN exec_failure e ON t.test_id = e.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "failed_hw_reset": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN hw_resets hr ON t.test_id = hr.test_id WHERE t.benchmark = ? AND s.class = 'failed'",
            "outlier_with_trap": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN traps tr ON t.test_id = tr.test_id WHERE t.benchmark = ? AND s.class = 'outlier'",
            "outlier_halt": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN halts h ON t.test_id = h.test_id WHERE t.benchmark = ? AND s.class = 'outlier'",
            "outlier_comm_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN comm_failure c ON t.test_id = c.test_id WHERE t.benchmark = ? AND s.class = 'outlier'",
            "outlier_SDC": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'outlier' AND s.SDC = 1",
            "outlier_exec_failure": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN exec_failure e ON t.test_id = e.test_id WHERE t.benchmark = ? AND s.class = 'outlier'",
            "outlier_hw_reset": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id JOIN hw_resets hr ON t.test_id = hr.test_id WHERE t.benchmark = ? AND s.class = 'outlier'"
        }
        clean_pass_query = '''
            SELECT COUNT(*) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN hw_resets hr ON t.test_id = hr.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND s.class = 'passed' AND s.SDC = 0
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND hr.test_id IS NULL
            AND e.test_id IS NULL
        '''
        clean_fail_query = '''
            SELECT COUNT(*) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN hw_resets hr ON t.test_id = hr.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND s.class = 'failed'
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND hr.test_id IS NULL
            AND e.test_id IS NULL
        '''

        clean_outlier_query = '''
            SELECT COUNT(*) FROM tests t
            JOIN status s ON t.test_id = s.test_id
            LEFT JOIN traps tr ON t.test_id = tr.test_id
            LEFT JOIN halts h ON t.test_id = h.test_id
            LEFT JOIN comm_failure c ON t.test_id = c.test_id
            LEFT JOIN hw_resets hr ON t.test_id = hr.test_id
            LEFT JOIN exec_failure e ON t.test_id = e.test_id
            WHERE t.benchmark = ? AND s.class = 'outlier' AND s.SDC = 0
            AND tr.test_id IS NULL AND h.test_id IS NULL
            AND c.test_id IS NULL AND hr.test_id IS NULL
            AND e.test_id IS NULL
        '''

        manual_check_queries = {
            "manual_passed": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'passed' AND t.needs_manual_check = 1",
            "manual_failed": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'failed' AND t.needs_manual_check = 1",
            "manual_outlier": "SELECT COUNT(*) FROM tests t JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.class = 'outlier' AND t.needs_manual_check = 1",
            "manual_missing": "SELECT COUNT(*) FROM tests t LEFT JOIN status s ON t.test_id = s.test_id WHERE t.benchmark = ? AND s.test_id IS NULL AND t.needs_manual_check = 1"
        }
        missing_status_query = '''
            SELECT COUNT(*) FROM tests t
            LEFT JOIN status s ON t.test_id = s.test_id
            WHERE t.benchmark = ? AND s.test_id IS NULL
        '''
        
        for name, query in status_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            raw_counts[name] = cursor.fetchone()[0]
        
        for name, query in event_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            raw_counts[name] = cursor.fetchone()[0]
        
        for name, query in combined_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            raw_counts[name] = cursor.fetchone()[0]

        for name, query in manual_check_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            raw_counts[name] = cursor.fetchone()[0]
        
        cursor = self._execute_query(clean_pass_query, (self.benchmark_name,))
        raw_counts["clean_pass"] = cursor.fetchone()[0]
        
        cursor = self._execute_query(clean_fail_query, (self.benchmark_name,))
        raw_counts["clean_fail"] = cursor.fetchone()[0]

        cursor = self._execute_query(clean_outlier_query, (self.benchmark_name,))
        raw_counts["clean_outlier"] = cursor.fetchone()[0]
        
        cursor = self._execute_query(missing_status_query, (self.benchmark_name,))
        raw_counts["missing_status"] = cursor.fetchone()[0]
        
        total_classified = raw_counts["passed"] + raw_counts["failed"] + raw_counts["outlier"]
        total_tests = raw_counts["total_tests"]
        coverage_pct = (total_classified / total_tests) * 100 if total_tests > 0 else 0
        
        coverage_table = PrettyTable()
        coverage_table.field_names = ["Total Tests", "Classified Tests", "Coverage", "Manual Check Needed", "Missing Status"]
        coverage_table.align = "l"
        
        manual_check_pct = (raw_counts["needs_manual_check"] / total_tests) * 100 if total_tests > 0 else 0
        missing_status_pct = (raw_counts["missing_status"] / total_tests) * 100 if total_tests > 0 else 0
        
        coverage_table.add_row([
            total_tests,
            total_classified,
            f"{coverage_pct:.2f}%",
            f"{raw_counts['needs_manual_check']} ({manual_check_pct:.2f}%)",
            f"{raw_counts['missing_status']} ({missing_status_pct:.2f}%)"
        ])
        print(coverage_table)
        
        validation_table = PrettyTable()
        validation_table.field_names = ["Category", "Raw Count", "Percentage"]
        validation_table.align = "l"
        
        for category in ["total_tests", "passed", "failed", "outlier", "needs_manual_check"]:
            count = raw_counts[category]
            pct = (count / raw_counts["total_tests"]) * 100 if raw_counts["total_tests"] > 0 else 0
            validation_table.add_row([category, count, f"{pct:.2f}%"])
        
        validation_table.add_row(["-" * 20, "-" * 10, "-" * 10])
        
        for event in ["with_trap", "halt", "comm_failure", "SDC", "exec_failure", "hw_reset"]:
            count = raw_counts[event]
            pct = (count / raw_counts["total_tests"]) * 100 if raw_counts["total_tests"] > 0 else 0
            validation_table.add_row([event, count, f"{pct:.2f}%"])
        
        validation_table.add_row(["-" * 20, "-" * 10, "-" * 10])
        
        for category in ["clean_pass", "clean_fail", "clean_outlier", "missing_status"]:
            count = raw_counts[category]
            pct = (count / raw_counts["total_tests"]) * 100 if raw_counts["total_tests"] > 0 else 0
            validation_table.add_row([category, count, f"{pct:.2f}%"])
        
        print(validation_table)

        print("\nNote: event counts may exceed total tests due to multiple events per test.")
        print("      (e.g., a test that has both a trap and an SDC would be counted in both columns)\n")

        # Create a cross-tab table with manual checks as a row
        crosstab_table = PrettyTable()
        crosstab_table.field_names = ["Status/Event", "trap", "halt", "comm_failure", "SDC", "exec_failure", "hw_reset", "Clean", "Row Sum", "Database Total"]
        crosstab_table.align = "l"

        # Calculate row sums for each status category
        passed_sum = raw_counts["passed_with_trap"] + raw_counts["passed_halt"] + raw_counts["passed_comm_failure"] + raw_counts["passed_SDC"] + raw_counts["passed_exec_failure"] + raw_counts["passed_hw_reset"] + raw_counts["clean_pass"]
        failed_sum = raw_counts["failed_with_trap"] + raw_counts["failed_halt"] + raw_counts["failed_comm_failure"] + raw_counts["failed_exec_failure"] + raw_counts["clean_fail"] + raw_counts["failed_SDC"] + raw_counts["failed_hw_reset"]
        outlier_sum = raw_counts["outlier_with_trap"] + raw_counts["outlier_halt"] + raw_counts["outlier_comm_failure"] + raw_counts["outlier_SDC"] + raw_counts["outlier_exec_failure"] + raw_counts["outlier_hw_reset"] + raw_counts["clean_outlier"]
        column_sum = raw_counts["with_trap"] + raw_counts["halt"] + raw_counts["comm_failure"] + raw_counts["SDC"] + raw_counts["exec_failure"] + raw_counts["hw_reset"] + (raw_counts["clean_pass"] + raw_counts["clean_fail"] + raw_counts["clean_outlier"])

        crosstab_table.add_row([
            "passed", 
            raw_counts["passed_with_trap"],
            raw_counts["passed_halt"],
            raw_counts["passed_comm_failure"],
            raw_counts["passed_SDC"],
            raw_counts["passed_exec_failure"],
            raw_counts["passed_hw_reset"],
            raw_counts["clean_pass"],
            passed_sum,  # Row sum
            raw_counts["passed"]  # Database total
        ])

        crosstab_table.add_row([
            "failed", 
            raw_counts["failed_with_trap"],
            raw_counts["failed_halt"],
            raw_counts["failed_comm_failure"],
            raw_counts["failed_SDC"],
            raw_counts["failed_exec_failure"],
            raw_counts["failed_hw_reset"],
            raw_counts["clean_fail"],
            failed_sum,  # Row sum
            raw_counts["failed"]  # Database total
        ])

        crosstab_table.add_row([
            "outlier", 
            raw_counts["outlier_with_trap"],
            raw_counts["outlier_halt"],
            raw_counts["outlier_comm_failure"],
            raw_counts["outlier_SDC"],
            raw_counts["outlier_exec_failure"],
            raw_counts["outlier_hw_reset"],
            raw_counts["clean_outlier"],
            outlier_sum,  # Row sum
            raw_counts["outlier"]  # Database total
        ])

        crosstab_table.add_row([
            "missing status", 
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            raw_counts["missing_status"]
        ])

        # Add the manual check row
        crosstab_table.add_row([
            "manual check",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A", 
            "N/A",
            "N/A",
            raw_counts["needs_manual_check"]
        ])

        crosstab_table.add_row([
            "Column Total", 
            raw_counts["with_trap"],
            raw_counts["halt"],
            raw_counts["comm_failure"],
            raw_counts["SDC"],
            raw_counts["exec_failure"],
            raw_counts["hw_reset"],
            raw_counts["clean_pass"] + raw_counts["clean_fail"] + raw_counts["clean_outlier"],
            column_sum,  # Column sum total
            raw_counts["total_tests"]  # Database total
        ])

        print(crosstab_table)
        print("\nNote: Row sums may exceed database totals due to tests with multiple events.")
        print("      (e.g., a test that has both a trap and an SDC would be counted in both columns)")
                
        # Calculate our calculated totals vs raw totals
        total_passed_combined = raw_counts["passed_with_trap"] + raw_counts["passed_halt"] + raw_counts["passed_comm_failure"] + raw_counts["clean_pass"] + raw_counts["passed_SDC"] + raw_counts["passed_exec_failure"] + raw_counts["passed_hw_reset"]
        total_failed_combined = raw_counts["failed_with_trap"] + raw_counts["failed_halt"] + raw_counts["failed_comm_failure"] + raw_counts["failed_exec_failure"] + raw_counts["clean_fail"] + raw_counts["failed_SDC"] + raw_counts["failed_hw_reset"]
        total_outlier_combined = raw_counts["outlier_with_trap"] + raw_counts["outlier_halt"] + raw_counts["outlier_comm_failure"] + raw_counts["outlier_exec_failure"] + raw_counts["clean_outlier"] + raw_counts["outlier_SDC"] + raw_counts["outlier_hw_reset"]
        
        overlapping_queries = {
            "passed_overlap": """
                SELECT COUNT(DISTINCT t.test_id) FROM tests t
                JOIN status s ON t.test_id = s.test_id
                WHERE t.benchmark = ? AND s.class = 'passed'
                AND (
                    (EXISTS(SELECT 1 FROM traps tr WHERE tr.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM halts h WHERE h.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM comm_failure c WHERE c.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM hw_resets hr WHERE hr.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM exec_failure e WHERE e.test_id = t.test_id) +
                     (s.SDC = 1)) > 1
                )
            """,
            "failed_overlap": """
                SELECT COUNT(DISTINCT t.test_id) FROM tests t
                JOIN status s ON t.test_id = s.test_id
                WHERE t.benchmark = ? AND s.class = 'failed'
                AND (
                    (EXISTS(SELECT 1 FROM traps tr WHERE tr.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM halts h WHERE h.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM comm_failure c WHERE c.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM hw_resets hr WHERE hr.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM exec_failure e WHERE e.test_id = t.test_id) +
                     (s.SDC = 1)) > 1
                )
            """,
            "outlier_overlap": """
                SELECT COUNT(DISTINCT t.test_id) FROM tests t
                JOIN status s ON t.test_id = s.test_id
                WHERE t.benchmark = ? AND s.class = 'outlier'
                AND (
                    (EXISTS(SELECT 1 FROM traps tr WHERE tr.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM halts h WHERE h.test_id = t.test_id) + 
                     EXISTS(SELECT 1 FROM comm_failure c WHERE c.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM hw_resets hr WHERE hr.test_id = t.test_id) +
                     EXISTS(SELECT 1 FROM exec_failure e WHERE e.test_id = t.test_id) +
                     (s.SDC = 1)) > 1
                )
            """
        }

        for name, query in overlapping_queries.items():
            cursor = self._execute_query(query, (self.benchmark_name,))
            raw_counts[name] = cursor.fetchone()[0]

        passed_expected_diff = raw_counts["passed_overlap"]
        failed_expected_diff = raw_counts["failed_overlap"]
        outlier_expected_diff = raw_counts["outlier_overlap"]

        passed_diff = total_passed_combined - raw_counts["passed"]
        failed_diff = total_failed_combined - raw_counts["failed"]
        outlier_diff = total_outlier_combined - raw_counts["outlier"] 

        overlap_table = PrettyTable()
        overlap_table.field_names = ["Category", "Database Total", "Sum of Events", "Difference", "Overlapping Tests", "Overlap Match?"]
        overlap_table.align = "l"

        overlap_table.add_row([
            "passed",
            raw_counts["passed"],
            total_passed_combined,
            passed_diff,
            raw_counts["passed_overlap"],
            "✓" if abs(passed_diff - passed_expected_diff) <= 1 else "✗"
        ])

        overlap_table.add_row([
            "failed",
            raw_counts["failed"],
            total_failed_combined,
            failed_diff,
            raw_counts["failed_overlap"],
            "✓" if abs(failed_diff - failed_expected_diff) <= 1 else "✗"
        ])

        overlap_table.add_row([
            "outlier",
            raw_counts["outlier"],
            total_outlier_combined,
            outlier_diff,
            raw_counts["outlier_overlap"],
            "✓" if abs(outlier_diff - outlier_expected_diff) <= 1 else "✗"
        ])

        print("\n==== OVERLAPPING EVENTS ANALYSIS ====")
        print(overlap_table)
        print("\nNote: If the difference between 'Sum of Events' and 'Database Total' matches 'Overlapping Tests',")
        print("      then it confirms the consistency of the counts (allowing for ±1 rounding errors).")

        print("\n==== COMPARING TO HIERARCHY COUNTS ====")
        hierarchy_counts = self.get_status_hierarchy_counts()
        
        comparison_table = PrettyTable()
        comparison_table.field_names = ["Category", "Raw Count", "Hierarchy Count", "Match?"]
        comparison_table.align = "l"
        
        key_comparisons = [
            ("passed.total", raw_counts["passed"], hierarchy_counts["passed"]["total"]),
            ("passed.clean", raw_counts["clean_pass"], hierarchy_counts["passed"]["clean"]),
            ("passed.trap", raw_counts["passed_with_trap"], hierarchy_counts["passed"]["trap"]),
            ("passed.halt", raw_counts["passed_halt"], hierarchy_counts["passed"]["halt"]),
            ("failed.total", raw_counts["failed"], hierarchy_counts["failed"]["total"]),
            ("failed.clean", raw_counts["clean_fail"], hierarchy_counts["failed"]["clean"]),
            ("failed.trap", raw_counts["failed_with_trap"], hierarchy_counts["failed"]["trap"]),
            ("failed.halt", raw_counts["failed_halt"], hierarchy_counts["failed"]["halt"])
        ]
        
        for desc, raw_val, hier_val in key_comparisons:
            comparison_table.add_row([desc, raw_val, hier_val, "✓" if raw_val == hier_val else "✗"])
            
        print(comparison_table)
        