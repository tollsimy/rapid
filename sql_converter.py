import os
import json
import sqlite3
import argparse
from typing import Dict, Any, List

class ResultsDBConverter:
    def __init__(self, db_path: str):
        """Initialize converter with a database path"""
        self.db_path = db_path
        self.conn = self._setup_database()

    def delete_database(self):
        self.conn.close()
        """Delete the database file"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print(f"Deleted database: {self.db_path}")
        else:
            print(f"Database not found: {self.db_path}")
        
    def _setup_database(self) -> sqlite3.Connection:
        """Create the database schema if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            test_id TEXT PRIMARY KEY,
            benchmark TEXT,
            bit_position INTEGER,
            output TEXT,
            wrong_res BOOLEAN,
            needs_manual_check BOOLEAN
        )
        ''')

        # =========== Status =============
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS status (
            test_id TEXT,
            status TEXT,
            PRIMARY KEY (test_id),
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        ''')
        
        # ============ Events =============

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS traps (
            test_id TEXT PRIMARY KEY,
            scause TEXT,
            sepc TEXT,
            stval TEXT,
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeouts (
            test_id TEXT PRIMARY KEY,
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS hw_resets (
            test_id TEXT PRIMARY KEY,
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS corrupted (
            test_id TEXT PRIMARY KEY,
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        ''')
        
        conn.commit()
        return conn

    def _get_benchmark_name(self, results_file: str) -> str:
        """Extract benchmark name from filename"""
        basename = os.path.basename(results_file)
        name = basename.split('_')[0]
        return name
    
    def import_json_to_db(self, results_file: str) -> int:
        """Import a JSON results file into the database"""
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
            
            benchmark = self._get_benchmark_name(results_file)
            
            cursor = self.conn.cursor()
            imported_count = 0
            
            self.conn.execute("BEGIN TRANSACTION")
            
            for test_id, test_data in data.items():
                bit_position = test_data.get('bit_position', None)
                output = test_data.get('output') is not None
                wrong_res = 1 if test_data.get('wrong_res', False) else 0
                needs_manual_check = 1 if test_data.get('needs_manual_check', False) else 0
                
                cursor.execute(
                    "INSERT OR REPLACE INTO tests VALUES (?, ?, ?, ?, ?, ?)",
                    (test_id, benchmark, bit_position, output, wrong_res, needs_manual_check)
                )
                
                cursor.execute(
                    "INSERT OR REPLACE INTO status VALUES (?, ?)",
                    (test_id, test_data.get('status'))
                )
                
                events = test_data.get('events', [])
                for event in events:
                    if event['type'] == 'trap':
                        trap_details = event['trap_details']
                        cursor.execute(
                            "INSERT OR REPLACE INTO trap_details VALUES (?, ?, ?, ?)",
                            (test_id, trap_details['scause'], trap_details['sepc'], trap_details['stval'])
                        )
                    elif event['type'] == 'timeout':
                        cursor.execute(
                            "INSERT OR REPLACE INTO timeouts VALUES (?)",
                            (test_id,)
                        )
                    elif event['type'] == 'hw_reset':
                        cursor.execute(
                            "INSERT OR REPLACE INTO hw_resets VALUES (?)",
                            (test_id,)
                        )
                    elif event['type'] == 'corrupted':
                        cursor.execute(
                            "INSERT OR REPLACE INTO corrupted VALUES (?)",
                            (test_id,)
                        )

                imported_count += 1
                
            self.conn.commit()
            print(f"Successfully imported {imported_count} test results for benchmark {benchmark}")
            return imported_count
            
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading results file: {e}")
            return 0
    
    def import_directory(self, directory: str, pattern: str = '*_results.json', recursive: bool = False) -> Dict[str, int]:
        """Import all matching JSON files from a directory"""
        import glob
        
        if recursive:
            pattern = os.path.join(directory, '**', pattern)
            json_files = glob.glob(pattern, recursive=True)
        else:
            pattern = os.path.join(directory, pattern)
            json_files = glob.glob(pattern)
        
        if not json_files:
            print(f"No matching JSON files found in {directory}")
            return {}
        
        print(f"Found {len(json_files)} JSON files to import")
        
        import_stats = {}
        for json_file in json_files:
            print(f"Importing {json_file}...")
            benchmark = self._get_benchmark_name(json_file)
            count = self.import_json_to_db(json_file)
            import_stats[benchmark] = count
        
        return import_stats
    
    def get_benchmarks(self) -> List[str]:
        """Get list of all benchmarks in the database"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT benchmark FROM tests")
        return [row[0] for row in cursor.fetchall()]
    
    def get_benchmark_stats(self) -> Dict[str, int]:
        """Get count of tests per benchmark"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT benchmark, COUNT(*) FROM tests GROUP BY benchmark")
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='Convert JSON test results to SQLite database')
    parser.add_argument('path', type=str, help='Path to JSON results file or directory containing JSON files')
    parser.add_argument('--db', type=str, default='fault_analysis.db', help='SQLite database path (default: fault_analysis.db)')
    parser.add_argument('--recursive', '-r', action='store_true', help='Search for JSON files recursively in directories')
    parser.add_argument('--pattern', type=str, default='*_results.json', help='Pattern for matching JSON files')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild database from scratch')
    
    args = parser.parse_args()
    
    converter = ResultsDBConverter(args.db)

    if args.rebuild:
        converter.delete_database()
        converter = ResultsDBConverter(args.db)
    
    if os.path.isdir(args.path):
        import_stats = converter.import_directory(
            args.path, 
            pattern=args.pattern, 
            recursive=args.recursive
        )
        
        if import_stats:
            print("\nImport Summary:")
            for benchmark, count in import_stats.items():
                print(f"  {benchmark}: {count} tests")
    else:
        if not os.path.exists(args.path):
            print(f"Error: File not found - {args.path}")
            converter.close()
            return
        
        count = converter.import_json_to_db(args.path)
        benchmark = converter._get_benchmark_name(args.path)
        print(f"\nImport Summary:")
        print(f"  {benchmark}: {count} tests")
    
    print("\nDatabase Summary:")
    benchmark_stats = converter.get_benchmark_stats()
    total_tests = sum(benchmark_stats.values())
    
    print(f"Total benchmarks: {len(benchmark_stats)}")
    print(f"Total tests: {total_tests}")
    
    for benchmark, count in benchmark_stats.items():
        print(f"  {benchmark}: {count} tests")
    
    converter.close()


if __name__ == "__main__":
    main()
