# Example of custom log format

TEST_NUMBER_PATTERN = r'_([0-9A-Za-z]+)(?:\s+(.*))?'
TEST_BLOCK_MARKER = "Starting test"
TEST_NAME_FORMAT = "{benchmark_type}_{test_num}"
BENCHMARK_PATTERN = r'inject/([a-zA-Z0-9_]+)/([a-zA-Z0-9_]+)_(\d+)'