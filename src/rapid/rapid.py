#!/usr/bin/python3

# ============================================================================ #
#
# RAPID: Reliability Analysis and Precision Injection Diagnostic
#
# ============================================================================ #

import argparse
import os
import sys
from typing import List
from .parser import ResultsParser, NoSuitableClassifierError
from .sql_converter import ResultsDBConverter
from .analyzer import ResultsAnalyzer  
from .visualizer import ResultsVisualizer
from .injecter import FaultInjecter
from .utils.candaguardia import CanDaGuardia

def setup_argparse():
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(
        description='RAPID: Reliability Analysis and Precision Injection Diagnostic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor a file for changes
  rapid.py --monitor --file output.log --alert-interval 30

  # Inject faults into a binary file
  rapid.py --inject --binary-file program --num-flips 10 --output-dir inject/
  
  # Parse log files and create JSON results
  rapid.py --parse-logs --log-dir logs/ --inject-dir inject/ --output-dir results/
  
  # Use custom classifiers
  rapid.py --parse-logs --log-file log.txt --inject-file inject.json --classifier my_classifier.py
  
  # List available classifiers (built-in and custom)
  rapid.py --list-classifiers --classifier custom_classifier.py
  
  # Use multiple custom classifiers from a directory
  rapid.py --parse-logs --log-dir logs/ --inject-dir inject/ --classifier-dir ./my_classifiers/
  
  # Import results to database
  rapid.py --import-results --results-dir results/ --db fault_analysis.db
  
  # Analyze all benchmarks in database
  rapid.py --analyze --db fault_analysis.db --all-benchmarks
  
  # Full pipeline: parse logs, import to DB, and analyze
  rapid.py --full-pipeline --log-dir logs/ --inject-dir inject/ --db fault_analysis.db --classifier-dir my_classifiers/
        """
    )
    
    input_group = parser.add_argument_group('Input Options')
    db_group = parser.add_argument_group('Database Options')
    analysis_group = parser.add_argument_group('Analysis Options')
    output_group = parser.add_argument_group('Output Options')
    inject_group = parser.add_argument_group('Fault Injection Options')
    monitor_group = parser.add_argument_group('File Monitoring Options')

    # Pipeline options
    parser.add_argument('--inject', action='store_true',
                      help='Inject faults into binary file')
    parser.add_argument('--parse-logs', action='store_true',
                      help='Parse raw log files into structured JSON results')
    parser.add_argument('--import-results', action='store_true',
                      help='Import JSON results into the database')
    parser.add_argument('--analyze', action='store_true',
                      help='Analyze results from the database')
    parser.add_argument('--full-pipeline', action='store_true',
                      help='Run the complete pipeline: parse logs, import to DB, and analyze')
    parser.add_argument('--monitor', action='store_true',
                      help='Monitor a file for changes and alert when it becomes stuck')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose output')
    
    # Fault injection options
    inject_group.add_argument('--binary-file', type=str,
                      help='Binary file to inject faults into')
    inject_group.add_argument('--num-flips', type=int, default=10,
                      help='Number of bit flips to inject (default: 10)')
    inject_group.add_argument('--seed', type=int,
                      help='Random seed for reproducible fault injection')
    
    # Input options
    input_group.add_argument('--classifier', action='append', dest='custom_classifiers',
                      help='Path to a Python file containing custom classifier implementation')
    input_group.add_argument('--classifier-dir', dest='classifier_dirs', action='append',
                      help='Directory containing Python files with custom classifier implementations')
    input_group.add_argument('--list-classifiers', action='store_true',
                      help='List all available classifiers')
    input_group.add_argument('--log-dir', type=str,
                      help='Directory containing log files')
    input_group.add_argument('--log-file', type=str,
                      help='Single log file to process')
    input_group.add_argument('--inject-dir', type=str,
                      help='Directory containing injection JSON files')
    input_group.add_argument('--inject-file', type=str,
                      help='Single injection JSON file to process')
    input_group.add_argument('--results-dir', type=str, default='results',
                      help='Directory containing result JSON files (default: results)')
    input_group.add_argument('--results-file', type=str,
                      help='Single result JSON file to process')
    input_group.add_argument('--log-format', '-f', type=str,
                      help='Path to log_format.py file containing custom patterns')
    
    # Database options
    db_group.add_argument('--db', type=str, default='fault_analysis.db',
                      help='Path to SQLite database (default: fault_analysis.db)')
    db_group.add_argument('--create-db', action='store_true',
                      help='Create a new database (will overwrite existing)')
    db_group.add_argument('--list-benchmarks', action='store_true',
                      help='List available benchmarks in the database')
    
    # Analysis options
    analysis_group.add_argument('--benchmark', type=str,
                      help='Specific benchmark to analyze')
    analysis_group.add_argument('--all-benchmarks', action='store_true',
                      help='Analyze all benchmarks in the database')
    analysis_group.add_argument('--status', type=str,
                      help='Filter tests by status (e.g., trap, halt)')
    
    # Output options
    output_group.add_argument('--output-dir', type=str, default='plots',
                      help='Directory to save output files (default: plots)')
    output_group.add_argument('--combined', action='store_true',
                      help='Create combined visualizations for all benchmarks')
    output_group.add_argument('--skip-plots', action='store_true',
                      help='Skip generating plots')
    output_group.add_argument('--text-only', action='store_true',
                      help='Only output text summaries (no graphical plots)')
    
    monitor_group.add_argument('--file', type=str,
                      help='File to monitor for changes')
    monitor_group.add_argument('--alert-interval', type=int, default=50,
                      help='Alert interval in seconds when file is stuck (default: 50)')
    monitor_group.add_argument('--sound-file', type=str,
                      default="/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
                      help='Sound file to play when file is stuck')
    
    return parser

def find_matching_files(directory: str, pattern: str = None, extension: str = None) -> List[str]:
    """Find files matching pattern and/or extension in directory"""
    if not os.path.isdir(directory):
        print(f"Error: Directory not found: {directory}")
        return []
    
    files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            if extension and not filename.endswith(extension):
                continue
            if pattern and pattern not in filename:
                continue
            files.append(filepath)
    
    return files

def parse_logs(args):
    """Parse benchmark output logs"""
    if not args.log_file and not args.log_dir:
        print("Error: Must specify either --log-file or --log-dir")
        print("  Example: ./rapid.py --parse-logs --log-file tests.log --inject-file inject/matmul_bitflips.json --log-format my_log_format.py")
        return False
        
    if not args.inject_file and not args.inject_dir:
        print("Error: Must specify either --inject-file or --inject-dir")
        print("  Example: ./rapid.py --parse-logs --log-file tests.log --inject-file inject/matmul_bitflips.json --log-format my_log_format.py")
        return False
        
    if (args.log_file and not args.inject_file) or (args.inject_file and not args.log_file):
        print("Error: Must specify either --log-file and --inject-file OR --log-dir and --inject-dir")
        print("  Example: ./rapid.py --parse-logs --log-file tests.log --inject-file inject/matmul_bitflips.json --log-format my_log_format.py")
        print("\nRequired parameters:")
        print("  --log-format <file.py>     : Patterns for parsing the log file")
        print("\nOptional classifier parameters:")
        print("  --classifier <file.py>      : Use a custom classifier")
        print("  --classifier-dir <dir>      : Use all classifiers in directory")
        return False
        
    if (args.log_dir and not args.inject_dir) or (args.inject_dir and not args.log_dir):
        print("Error: Must specify either --log-file and --inject-file OR --log-dir and --inject-dir")
        print("  Example: ./rapid.py --parse-logs --log-dir logs/ --inject-dir inject/ --log-format my_log_format.py")
        print("\nRequired parameters:")
        print("  --log-format <file.py>     : Patterns for parsing the log file")
        print("\nOptional classifier parameters:")
        print("  --classifier <file.py>      : Use a custom classifier")
        print("  --classifier-dir <dir>      : Use all classifiers in directory")
        return False
    
    if not args.log_format:
        print("Error: Must specify --log-format with log patterns")
        print("\nUsage example:")
        print("  ./rapid.py --parse-logs --log-file tests.log --inject-file inject.json --log-format my_log_format.py")
        return False

    custom_patterns = {}
    if args.log_format:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("log_format", args.log_format)
            if spec is not None:
                log_format = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(log_format)
                
                # Extract patterns from log_format.py
                pattern_vars = ['TEST_NUMBER_PATTERN', 'TEST_BLOCK_MARKER', 
                              'TEST_NAME_FORMAT', 'BENCHMARK_PATTERN']
                
                for var in pattern_vars:
                    if hasattr(log_format, var):
                        custom_patterns[var.lower()] = getattr(log_format, var)
                        if args.verbose:
                            print(f"Using custom {var}: {custom_patterns[var.lower()]}")
        except Exception as e:
            print(f"Error loading log format file: {e}")

    try:
        parser = ResultsParser(
            custom_classifiers=args.custom_classifiers,
            classifier_dirs=args.classifier_dirs,
            test_number_pattern=custom_patterns.get('test_number_pattern'),
            test_block_marker=custom_patterns.get('test_block_marker'),
            test_name_format=custom_patterns.get('test_name_format'),
            benchmark_pattern=custom_patterns.get('benchmark_pattern')
        )
    except Exception as e:
        print(f"Error initializing parser: {e}")
        return False

    parsed_files = 0
    
    if args.log_file and args.inject_file:
        if not os.path.exists(args.log_file) or not os.path.exists(args.inject_file):
            print(f"Error: Log file or inject file not found")
            return False
        
        print(f"Processing log file: {args.log_file}")
        try:
            results_file = parser.process_log_file(args.log_file, args.inject_file, args.results_dir)
            if results_file:
                parsed_files += 1
                print(f"Results saved to: {results_file}")
        except NoSuitableClassifierError:
            return False
        except Exception as e:
            print(f"Error processing file: {e}")
            return False
    
    elif args.log_dir and args.inject_dir:
        if not os.path.isdir(args.log_dir) or not os.path.isdir(args.inject_dir):
            print(f"Error: Log directory or inject directory not found")
            return False
        
        log_files = find_matching_files(args.log_dir, extension='.txt')
        if not log_files:
            print(f"No log files found in {args.log_dir}")
            return False
        
        inject_files = find_matching_files(args.inject_dir, extension='.json')
        if not inject_files:
            print(f"No inject files found in {args.inject_dir}")
            return False
        
        processed_pairs = []
        
        for log_file in log_files:
            log_basename = os.path.basename(log_file).split('.')[0]
            best_match = None
            best_score = 0
            
            for inject_file in inject_files:
                inject_basename = os.path.basename(inject_file).split('.')[0]
                
                # Simple matching heuristic: count common substrings
                score = 0
                for part in log_basename.split('_'):
                    if part in inject_basename:
                        score += len(part)
                
                if score > best_score:
                    best_score = score
                    best_match = inject_file
            
            if best_match and best_score > 3:  # Minimum matching threshold
                processed_pairs.append((log_file, best_match))
        
        for log_file, inject_file in processed_pairs:
            print(f"Processing log file: {log_file}")
            print(f"  with inject file: {inject_file}")
            
            try:
                results_file = parser.process_log_file(log_file, inject_file, args.results_dir)
                if results_file:
                    parsed_files += 1
                    if args.verbose:
                        print(f"  Results saved to: {results_file}")
            except Exception as e:
                print(f"  Error processing files: {e}")
    
    else:
        print("Error: Must specify either --log-file and --inject-file OR --log-dir and --inject-dir")
        print("  Example: ./RAPID.py --parse-logs --log-file tests.log --inject-file inject/matmul_bitflips.json")
        return False
    
    print(f"Parsing complete. Processed {parsed_files} files.")
    return parsed_files > 0

def import_to_database(args):
    """Import results to database using ResultsDBConverter"""
    if ResultsDBConverter is None:
        print("Error: ResultsDBConverter module not found. Cannot import to database.")
        return False
    
    converter = ResultsDBConverter(args.db)

    if args.create_db:
        converter.delete_database()
        converter.create_database()
    
    imported_files = 0
    
    if args.results_file:
        if not os.path.exists(args.results_file):
            print(f"Error: Results file not found: {args.results_file}")
            return False
        
        print(f"Importing file: {args.results_file}")
        if converter.import_json_to_db(args.results_file):
            imported_files += 1
    
    elif args.results_dir:
        if not os.path.isdir(args.results_dir):
            print(f"Error: Results directory not found: {args.results_dir}")
            return False
        
        result_files = find_matching_files(args.results_dir, extension='_results.json')
        if not result_files:
            print(f"No result files found in {args.results_dir}")
            return False
        
        for result_file in result_files:
            print(f"Importing file: {result_file}")
            try:
                if converter.import_json_to_db(result_file):
                    imported_files += 1
            except Exception as e:
                print(f"  Error: {e}")
    
    else:
        print("Error: Must specify either --results-file or --results-dir")
        return False
    
    print(f"Import complete. Imported {imported_files} files to database.")
    return imported_files > 0

def analyze_results(args):
    """Analyze results using ResultsAnalyzer and ResultsVisualizer"""
    if ResultsAnalyzer is None:
        print("Error: ResultsAnalyzer module not found. Cannot analyze results.")
        return False
    
    if not os.path.exists(args.db):
        print(f"Error: Database file not found: {args.db}")
        return False
    
    os.makedirs(args.output_dir, exist_ok=True)
    temp_analyzer = ResultsAnalyzer(args.db)
    
    if args.list_benchmarks:
        benchmarks = temp_analyzer.get_available_benchmarks()
        print("\nAvailable benchmarks in database:")
        for i, benchmark in enumerate(benchmarks, 1):
            print(f"  {i}. {benchmark}")
        return True
    
    benchmarks_to_analyze = []
    if args.benchmark:
        benchmarks_to_analyze = [args.benchmark]
    elif args.all_benchmarks:
        benchmarks_to_analyze = temp_analyzer.get_available_benchmarks()
    else:
        benchmarks = temp_analyzer.get_available_benchmarks()
        if not benchmarks:
            print("No benchmarks found in database!")
            return False
            
        print("\nAvailable benchmarks:")
        for i, benchmark in enumerate(benchmarks, 1):
            print(f"  {i}. {benchmark}")
        
        try:
            choice = input("\nEnter benchmark number to analyze (or empty for 'all'): ")
            if not choice:
                choice = 'all'
            if choice.lower() == 'all':
                benchmarks_to_analyze = benchmarks
            else:
                idx = int(choice) - 1
                if 0 <= idx < len(benchmarks):
                    benchmarks_to_analyze = [benchmarks[idx]]
                else:
                    print("Invalid selection!")
                    return False
        except (ValueError, IndexError):
            print("Invalid selection!")
            return False
        
    all_analyzers = []
    
    for benchmark in benchmarks_to_analyze:
        print(f"\n{'='*60}")
        print(f"Analyzing benchmark: {benchmark}")
        print(f"{'='*60}")
        
        analyzer = ResultsAnalyzer(args.db, benchmark)
        all_analyzers.append(analyzer)
        
        if args.status:
            tests = analyzer.find_tests_with_status(args.status)
            print(f"\nTests with status '{args.status}':")
            for test in tests:
                print(f"  {test}")
            print(f"Found {len(tests)} tests with '{args.status}' status")
        
        analyzer.print_summary()
        
        if not args.skip_plots and not args.text_only and ResultsVisualizer is not None:
            print("\nGenerating visualizations...")
            visualizer = ResultsVisualizer(args.output_dir)
            
            bit_position_stats = analyzer.analyze_by_bit_position()
            visualizer.plot_bit_position_impact(bit_position_stats, benchmark)
            
            counts = analyzer.get_status_hierarchy_counts()
            coverage = analyzer.analyze_test_coverage()
            total_tests = coverage["total_tests"]
            visualizer.plot_status_hierarchy_bars(counts, total_tests, benchmark)
    
    if (args.combined and len(all_analyzers) > 1 and 
        not args.skip_plots and not args.text_only and 
        ResultsVisualizer is not None):
        
        print("\nCreating combined visualizations for all benchmarks...")
        
        benchmark_data = {}
        for analyzer in all_analyzers:
            benchmark_name = analyzer.benchmark_name
            benchmark_data[benchmark_name] = {
                'analyzer': analyzer,
                'status_counts': analyzer.count_by_status(),
                'bit_position_stats': analyzer.analyze_by_bit_position(),
                'hierarchy_counts': analyzer.get_status_hierarchy_counts(),
                'total_tests': analyzer.analyze_test_coverage()["total_tests"]
            }

        create_combined_visualizations(benchmark_data, args.output_dir)
    
    print("\nAnalysis complete!")
    return True

def create_combined_visualizations(benchmark_data, output_dir):
    """Create combined visualizations across multiple benchmarks"""
    if ResultsVisualizer is None:
        print("Warning: ResultsVisualizer module not found. Cannot create combined visualizations.")
        return
        
    visualizer = ResultsVisualizer(output_dir)

    if hasattr(visualizer, 'plot_trap_causes_comparison'):
        analyzers = {name: data['analyzer'] for name, data in benchmark_data.items()}
        visualizer.plot_trap_causes_comparison(analyzers, top_n=5)

def inject_faults(args):
    """Inject faults into binary file using FaultInjecter"""
    if FaultInjecter is None:
        print("Error: FaultInjecter module not found. Cannot inject faults.")
        return False
    
    if not args.binary_file:
        print("Error: Must specify --binary-file for fault injection")
        return False
    
    if not os.path.exists(args.binary_file):
        print(f"Error: Binary file not found: {args.binary_file}")
        return False
    
    output_dir = args.output_dir if args.output_dir else "inject"
    
    print(f"Injecting {args.num_flips} faults into {args.binary_file}")
    
    injecter = FaultInjecter()
    
    try:
        json_path = injecter.inject_and_save(
            args.binary_file, 
            args.num_flips,
            output_dir,
            args.seed
        )
        print(f"Fault injection complete. Information saved to {json_path}")
        return True
    except Exception as e:
        print(f"Error during fault injection: {e}")
        return False

def monitor_file(args):
    """Monitor a file for changes and alert when it becomes stuck"""
    
    if not args.file:
        print("Error: Must specify --file to monitor")
        return False
    
    try:
        monitor = CanDaGuardia(args.sound_file)
        monitor.monitor(args.file, args.alert_interval, args.verbose)
        return True
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"Error during monitoring: {e}")
        return False


def main():
    parser = setup_argparse()
    args = parser.parse_args()
    
    if args.inject:
        if FaultInjecter is None:
            print("Error: FaultInjecter module required for fault injection")
            return 1
    
    if args.parse_logs or args.full_pipeline or args.list_classifiers:
        if ResultsParser is None:
            print("Error: ResultsParser module required for log parsing")
            return 1
        
        if args.list_classifiers:
            print("\nLoading classifiers...")
            try:
                classifiers = ResultsParser.get_all_classifiers(
                    args.custom_classifiers, 
                    args.classifier_dirs
                )
                print("\nAvailable classifiers:")
                print("-" * 20)
                
                # Group classifiers as built-in or custom
                built_in = []
                custom = []
                
                for name, classifier in classifiers.items():
                    if classifier.__class__.__module__.startswith('classifiers.benchmark_classifiers'):
                        built_in.append(name)
                    else:
                        custom.append(name)
                
                if built_in:
                    print("Built-in classifiers:")
                    for name in sorted(built_in):
                        print(f"  - {name}")
                
                if custom:
                    print("\nCustom classifiers:")
                    for name in sorted(custom):
                        print(f"  - {name}")
                
                if not classifiers:
                    print("  No classifiers found")
                    
            except Exception as e:
                print(f"Error loading classifiers: {e}")
            return 0
    
    if args.import_results or args.full_pipeline:
        if ResultsDBConverter is None:
            print("Error: ResultsDBConverter module required for database import")
            return 1
    
    if args.analyze or args.full_pipeline:
        if ResultsAnalyzer is None:
            print("Error: ResultsAnalyzer module required for analysis")
            return 1
    
    print("\n" + "=" * 75)
    print("RAPID: Reliability Analysis and Precision Injection Diagnostic")
    print("=" * 75 + "\n")
    
    if args.monitor:
        return 0 if monitor_file(args) else 1
    
    if args.inject:
        if not inject_faults(args):
            return 1
    
    if args.full_pipeline:
        print("Running full pipeline: parse logs, import to DB, and analyze")
        
        if not parse_logs(args):
            print("Error in log parsing step. Pipeline aborted.")
            return 1
            
        if not import_to_database(args):
            print("Error in database import step. Pipeline aborted.")
            return 1
            
        if not analyze_results(args):
            print("Error in analysis step.")
            return 1
    
    else:
        if args.parse_logs:
            if not parse_logs(args):
                return 1
                
        if args.import_results:
            if not import_to_database(args):
                return 1
                
        if args.analyze or args.list_benchmarks:
            if not analyze_results(args):
                return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())