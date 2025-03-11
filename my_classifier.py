# Example custom classifier template

from benchmark_classifier import BenchmarkClassifierInterface
import re
from typing import Optional

class MyCustomClassifier(BenchmarkClassifierInterface):
    """
    Custom classifier for my benchmark
    This name will be used to identify the benchmark type
    """
    def __init__(self):
        super().__init__()
        self.name = "my_benchmark"
    
    def get_name(self) -> str:
        """Return benchmark type name"""
        return self.name
    
    def get_trap(self, output: str) -> Optional[int]:
        """Return trap value if present, otherwise None"""
        if "trap" in output:
            scause_match = re.search(r"scause\s+(0x[0-9a-fA-F]+)", output)
            if scause_match:
                try:
                    return int(scause_match.group(1), 16)
                except ValueError:
                    pass
        return None
    
    def get_trap_address(self, output: str) -> Optional[str]:
        """Return trap address if present, otherwise None"""
        sepc_match = re.search(r"sepc=(0x[0-9a-fA-F]+)", output)
        if sepc_match:
            return sepc_match.group(1)
        return None

    def get_trap_val(self, output: str) -> Optional[str]:
        """Return trap value if present, otherwise None"""
        scause_match = re.search(r"stval=(0x[0-9a-fA-F]+)", output)
        if scause_match:
            return scause_match.group(1)
        return None
    
    def get_halt(self, output: str) -> bool:
        """Check if halt/timeout occurred"""
        return "timed out" in output
    
    def get_comm_failure(self, output: str) -> bool:
        """Check if communication failure occurred"""
        return bool(re.search(r'[^\x20-\x7E\n\r\t]', output) or  # Non-printable ASCII
                   re.search(r'(�|\\x[0-9a-fA-F]{2})', output))   # Replacement chars
    
    def get_exec_failure(self, output: str) -> bool:
        """Check if execution failure occurred"""
        return "exit status=1" in output
    
    def get_hw_reset(self, output: str) -> bool:
        """Check if hardware reset occurred"""
        return "hw-reset" in output
    
    def get_result(self, output: str) -> int:
        """
        Return result code: 0=passed, 1=failed, 2=outlier
        """
        if "SUCCESS" in output:
            return 0
        elif "ERROR" in output:
            return 1
        
        if self.get_halt(output) or self.get_comm_failure(output):
            return 1
            
        return 2
    
    def get_sdc(self, output: str) -> bool:
        """Check if silent data corruption occurred"""

        return "INCORRECT_RESULT" in output