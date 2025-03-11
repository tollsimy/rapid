import re
from abc import ABC, abstractmethod
from typing import Optional

class BenchmarkClassifierInterface(ABC):
    
    @abstractmethod
    def get_name(self) -> str:
        """Return benchmark type name"""
        pass
    
    @abstractmethod
    def get_trap(self, output: str) -> Optional[int]:
        """
        Detect if a trap occurred
        
        Returns:
            Integer scause value if trap detected, None otherwise
        """
        pass
    
    @abstractmethod
    def get_trap_address(self, output: str) -> Optional[str]:
        """
        Extract trap address if available
        
        Returns:
            Trap address as string, or None if not found
        """
        pass
    
    @abstractmethod
    def get_halt(self, output: str) -> bool:
        """
        Detect if test halted or timed out
        
        Returns:
            True if halt detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_comm_failure(self, output: str) -> bool:
        """
        Detect if communication failure occurred
        
        Returns:
            True if communication failure detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_exec_failure(self, output: str) -> bool:
        """
        Detect if execution failure occurred
        
        Returns:
            True if execution failure detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_hw_reset(self, output: str) -> bool:
        """
        Detect if hardware reset occurred
        
        Returns:
            True if hardware reset detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_sdc(self, output: str) -> bool:
        """
        Detect if silent data corruption occurred
        
        Returns:
            True if SDC detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_result(self, output: str) -> int:
        """
        Determine the classification of the output
        
        Returns:
            Classification result: 0 for pass, 1 for fail, -1 for outlier
        """
        pass