import re
import sys
import os
from typing import Dict, Any
import json

class NoSuitableClassifierError(Exception):
    """Exception raised when no suitable classifier is found for a benchmark."""
    pass

class ResultsParser:
    """Parser for test output logs that extracts test results and statuses"""
    
    TEST_NUMBER_PATTERN = None
    TEST_BLOCK_MARKER = None
    TEST_NAME_FORMAT = None
    BENCHMARK_PATTERN = None
    
    def __init__(self, custom_classifiers=None, classifier_dirs=None, 
                 test_number_pattern=None, test_block_marker=None, 
                 test_name_format=None, benchmark_pattern=None):
        """
        Initialize parser with optional custom patterns
        
        Args:
            custom_classifiers: List of paths to Python files with custom classifiers
            classifier_dirs: List of directories containing classifier Python files
            test_number_pattern: Custom regex pattern for extracting test numbers
            test_block_marker: Custom marker for identifying the start of a test block
            test_name_format: Custom format string for generating test names
            path_pattern: Custom regex pattern for extracting benchmark type from path
        """
        self.classifiers = ResultsParser.get_all_classifiers(custom_classifiers, classifier_dirs)
        
        # Allow custom patterns to be set during initialization
        if test_number_pattern:
            self.TEST_NUMBER_PATTERN = test_number_pattern
        if test_block_marker:
            self.TEST_BLOCK_MARKER = test_block_marker
        if test_name_format:
            self.TEST_NAME_FORMAT = test_name_format
        if benchmark_pattern:
            self.BENCHMARK_PATTERN = benchmark_pattern
    
    @staticmethod
    def clean_test_number(num_str: str) -> str:
        """Clean test number by removing non-digit characters"""
        return ''.join(c for c in num_str if c.isdigit())
    
    @staticmethod
    def load_external_classifier(file_path):
        """Load a classifier from an external Python file"""
        import importlib.util
        import os
        
        try:
            module_name = os.path.basename(file_path).replace('.py', '')
            
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None:
                print(f"Could not load classifier from {file_path}")
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    attr.__module__ == module_name and
                    hasattr(attr, '__bases__') and
                    'BenchmarkClassifierInterface' in [base.__name__ for base in attr.__bases__]):
                    classifier = attr()
                    print(f"Loaded external classifier: {classifier.name}")
                    return classifier
                    
            print(f"No valid classifier found in {file_path}")
            return None
        except Exception as e:
            print(f"Error loading classifier from {file_path}: {e}")
            return None

    @staticmethod
    def get_all_classifiers(custom_files=None, custom_dirs=None) -> Dict[str, Any]:
        """
        Get all available user-defined classifiers 
        
        Args:
            custom_files: List of paths to Python files containing custom classifiers
            custom_dirs: List of directories containing Python files with custom classifiers
        """
        
        classifiers = {}
        
        if custom_files:
            for file_path in custom_files:
                if os.path.isfile(file_path) and file_path.endswith('.py'):
                    classifier = ResultsParser.load_external_classifier(file_path)
                    if classifier:
                        classifiers[classifier.name.lower()] = classifier
        
        if custom_dirs:
            for dir_path in custom_dirs:
                if os.path.isdir(dir_path):
                    for filename in os.listdir(dir_path):
                        if filename.endswith('.py'):
                            file_path = os.path.join(dir_path, filename)
                            classifier = ResultsParser.load_external_classifier(file_path)
                            if classifier:
                                classifiers[classifier.name.lower()] = classifier
        
        return classifiers

    @staticmethod
    def _build_status_dict(classifier, output: str) -> Dict[str, Any]:
        """
        Build status dictionary from classifier methods
        
        Args:
            classifier: The benchmark classifier
            output: The output text to classify
            
        Returns:
            Tuple of status_dict
        """

        events = []
        
        # Check for trap
        trap_value = classifier.get_trap(output)
        if trap_value is not None:
            trap_info = {"type": "trap", "scause": trap_value, "sepc": None, "stval": None}
            trap_addr = classifier.get_trap_address(output)
            trap_val = classifier.get_trap_val(output)
            if trap_addr:
                trap_info["sepc"] = trap_addr
            if trap_val:
                trap_info["stval"] = trap_val
            events.append(trap_info)
        
        # Check for other events
        if classifier.get_halt(output):
            events.append({"type": "halt"})
            
        if classifier.get_comm_failure(output):
            events.append({"type": "comm_failure"})
            
        if classifier.get_exec_failure(output):
            events.append({"type": "exec_failure"})
            
        if classifier.get_hw_reset(output):
            events.append({"type": "hw-reset"})
        
        # Convert result code to class string
        result_code = classifier.get_result(output)
        class_str = "passed" if result_code == 0 else "failed" if result_code == 1 else "outlier"
        
        # Create status dict
        status = {
            "class": class_str,
            "SDC": classifier.get_sdc(output),
            "events": events
        }
        
        return status

    def parse_output_file(self, output_path: str, input_json_file: str) -> Dict[str, Any]:
        """
        Parse the output log file and extract test results.
        
        Args:
            output_path: Path to the log file to parse
            input_json_file: Path to the original JSON with test specifications
            
        Returns:
            Dict mapping test IDs to their results
        """
        input_filename = os.path.basename(input_json_file).lower()
        detected_benchmarks = []
        benchmark_type = ""
        classifier = None
        
        # First pass: check for exact benchmark name matches in filename
        for _, cls in self.classifiers.items():
            name = cls.get_name()
            if name in input_filename:
                benchmark_type = name
                classifier = cls
                detected_benchmarks.append(name)
        
        # If multiple benchmarks detected, use the most specific one (longest name)
        if len(detected_benchmarks) > 1:
            benchmark_type = max(detected_benchmarks, key=len)
            classifier = self.classifiers[benchmark_type]
            print(f"Multiple benchmark types detected in filename '{input_filename}', using '{benchmark_type}'")
        
        if not classifier:
            print(f"\nError: No suitable classifier found for '{input_filename}'")
            print(f"Make sure a suitable classifier exists and all methods are implemented.")
            print("\nAvailable classifiers:")
            for name in sorted(self.classifiers.keys()):
                print(f"  - {name}")
            print("\nYou can specify a custom classifier using '--classifier' or '--classifier-dir'")
            print("   Example: --classifier my_custom_classifier.py\n")
            raise NoSuitableClassifierError(f"No suitable classifier found for '{input_filename}'")
        
        print(f"Using classifier '{benchmark_type}' for file '{input_filename}'")
        
        try:
            with open(input_json_file, 'r') as f:
                input_data = json.load(f)
        except Exception as e:
            print(f"Error reading input JSON file: {e}")
            return {}
            
        with open(output_path, 'r', encoding='ascii', errors='replace') as f:
            content = f.read()
        
        # Parse test blocks using the configurable marker
        test_blocks = content.split(f'\n{self.TEST_BLOCK_MARKER}')
        test_results = {}
        
        for block in test_blocks[1:]:
            lines = block.strip().split('\n')
            if not lines:
                continue
                
            first_line = lines[0].strip()
            
            actual_benchmark_type = re.search(self.BENCHMARK_PATTERN, first_line)   

            if actual_benchmark_type:
                actual_benchmark_type = actual_benchmark_type.group(1).lower()  # e.g., "coremark"
                
                # Check if this is a different benchmark type than expected
                if actual_benchmark_type != benchmark_type:                
                    # Get the appropriate classifier for this benchmark type
                    for name, cls in self.classifiers.items():
                        if name == actual_benchmark_type:
                            benchmark_type = actual_benchmark_type
                            classifier = cls
                            break
            
            test_num_match = re.search(self.TEST_NUMBER_PATTERN, first_line) 
            
            if not test_num_match:
                continue
                
            test_num = ResultsParser.clean_test_number(test_num_match.group(1))
            args = test_num_match.group(2) if test_num_match.lastindex >= 2 else ""
            
            test_name = self.TEST_NAME_FORMAT.format(benchmark_type=benchmark_type, test_num=test_num)
            
            output_lines = []
            for line in lines[1:]:
                if line.startswith(self.TEST_BLOCK_MARKER):
                    break
                if line.strip():
                    output_lines.append(line.strip())
            
            full_output = '\n'.join(output_lines)
            
            status_dict = self._build_status_dict(classifier, full_output)

            result = {
                "args": args.strip() if args else "",
                "output": full_output,
                "status": status_dict
            }
            
            test_results[test_name] = result

        missing_entries = []
        for key in input_data:
            if key not in test_results:
                print(f"Warning: Test {key} not found in log file, probable comm_failure output")
                missing_entries.append(key)
        
        if missing_entries:
            for key in missing_entries:
                test_results[key] = {
                    "args": "",
                    "output": "",
                    "status": {}
                }
                     
        required_fields = {'args', 'output', 'status'}
        
        for test_name, result in test_results.items():
            missing_fields = required_fields - set(result.keys())
            needs_manual_check = False
            if missing_fields:
                print(f"Warning: Test {test_name} is missing required fields: {missing_fields}")
                # Set defaults for missing fields
                for field in missing_fields:
                    if field == 'args':
                        result[field] = ""
                        needs_manual_check = True
                    elif field == 'output':
                        result[field] = "Missing output data"
                        needs_manual_check = True
                    elif field == 'status':
                        result[field] = {}       
                        needs_manual_check = True            
            if not result.get("output"):
                needs_manual_check = True
            result["needs_manual_check"] = needs_manual_check
                
        return test_results

    @staticmethod
    def update_json_file(json_path: str, test_results: Dict[str, Any], output_path: str) -> None:
        """
        Update the original JSON with test results and save to a new file.
        
        Args:
            json_path: Path to the original JSON file
            test_results: Dict mapping test IDs to their results
            output_path: Path to save the updated JSON
        """
        # Read existing JSON
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        output_data = {}
        
        for key in data:
            output_data[key] = data[key].copy() if isinstance(data[key], dict) else data[key]
            
            if key in test_results:
                output_data[key].update(test_results[key])
        
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

    @staticmethod
    def validate_parser(input_file: str, output_file: str) -> bool:
        """
        Validate that output JSON has same number of objects as input JSON
        and each object has the required new fields.
        
        Args:
            input_file: Path to the original JSON file
            output_file: Path to the updated JSON file
            
        Returns:
            True if validation passes, False otherwise
        """
        required_fields = {'args', 'output', 'status', 'needs_manual_check'}
        
        try:
            with open(input_file, 'r') as f:
                input_data = json.load(f)
            with open(output_file, 'r') as f:
                output_data = json.load(f)
            
            if len(input_data) != len(output_data):
                print(f"Error: Number of objects mismatch.")
                print(f"Input file has {len(input_data)} objects")
                print(f"Output file has {len(output_data)} objects")
                return False
            
            for key in input_data:
                if key not in output_data:
                    print(f"Error: Missing object {key} in output file")
                    return False
                    
            validation_failed = False
            for key, value in output_data.items():
                missing_fields = required_fields - set(value.keys())
                if missing_fields:
                    print(f"Error: Object {key} is missing required fields: {missing_fields}")
                    validation_failed = True
            
            if validation_failed:
                return False
                
            print("Validation passed successfully!")
            return True
            
        except FileNotFoundError as e:
            print(f"Error: Could not open file - {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format - {e}")
            return False
    
    def process_log_file(self, log_file: str, input_json_file: str, results_folder: str = "results") -> str:
        """
        Process a log file, extract results, and save them to a JSON file.
        
        Args:
            log_file: Path to the log file
            input_json_file: Path to the original JSON file
            results_folder: Folder to save results in
            
        Returns:
            Path to the generated results JSON file
        """
        os.makedirs(results_folder, exist_ok=True)
        
        results_json_file = os.path.join(
            results_folder, 
            os.path.basename(input_json_file).replace(".json", "_results.json")
        )
        
        test_results = self.parse_output_file(log_file, input_json_file)
        
        self.update_json_file(input_json_file, test_results, results_json_file)
        ResultsParser.validate_parser(input_json_file, results_json_file)
        
        return results_json_file

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='RAPID Parser - Process fault injection log files',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('log_file', help='Path to the log file to parse')
    parser.add_argument('inject_file', help='Path to the JSON file with test specifications')
    parser.add_argument('log_format', default=None,
                       help='Path to log_format.py file containing patterns')
    
    parser.add_argument('--output-dir', '-o', default='results', 
                       help='Directory to save result JSON files (default: results)')
    
    parser.add_argument('--classifier', '-c', action='append',
                       help='Path to custom classifier Python file')
    parser.add_argument('--classifier-dir', '-d', action='append',
                       help='Directory containing custom classifier Python files')
    args = parser.parse_args()
    
    custom_patterns = {}
    if args.log_format:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("log_format", args.log_format)
            if spec is not None:
                log_format = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(log_format)
                
                pattern_vars = ['TEST_NUMBER_PATTERN', 'TEST_BLOCK_MARKER', 
                               'TEST_NAME_FORMAT', 'BENCHMARK_PATTERN']
                
                for var in pattern_vars:
                    if hasattr(log_format, var):
                        custom_patterns[var.lower()] = getattr(log_format, var)
        except Exception as e:
            print(f"Error loading log format file: {e}")
    else:
        print("Error: No log format file provided")
        exit(1)
    
    # Initialize parser with options
    results_parser = ResultsParser(
        custom_classifiers=args.classifier,
        classifier_dirs=args.classifier_dir,
        test_number_pattern=custom_patterns.get('test_number_pattern'),
        test_block_marker=custom_patterns.get('test_block_marker'),
        test_name_format=custom_patterns.get('test_name_format'),
        benchmark_pattern=custom_patterns.get('benchmark_pattern')
    )
    
    # Process the log file
    result_file = results_parser.process_log_file(
        args.log_file, 
        args.inject_file,
        args.output_dir
    )
    
    print(f"Results saved to: {result_file}")


if __name__ == "__main__":
    main()