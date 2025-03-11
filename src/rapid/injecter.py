import os
import random
import json
from typing import Dict, List, Optional

class FaultInjecter:
    """
    A tool for injecting bit flips into binary files for fault injection testing.
    """
    
    def __init__(self):
        """Initialize the fault injecter."""
        pass
        
    def inject_bitflips(self, 
                       file_path: str, 
                       num_flips: int, 
                       out_folder: str, 
                       seed: Optional[int] = None) -> Dict[str, Dict]:
        """
        Inject random bit flips into a binary file.
        
        Parameters:
        -----------
        file_path : str
            Path to the binary file to modify
        num_flips : int
            Number of bit flips to inject
        out_folder : str
            Directory to store the modified files
        seed : int, optional
            Random seed for reproducibility
            
        Returns:
        --------
        Dict[str, Dict]
            Dictionary mapping output filenames to bit flip information
        """
        if seed is not None:
            random.seed(seed)
            
        filename = os.path.basename(file_path)[:5]
        
        print(f"Injecting {file_path} into {out_folder}/{filename}")
        
        with open(file_path, 'rb') as f:
            data = f.read()
        
        total_bits = len(data) * 8
        rand_bits = random.sample(range(0, total_bits), num_flips)
        rand_bits.sort()
        
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)
        
        bitflips = {}
        
        for i in range(len(rand_bits)):
            output_file = f"{filename}_{i}"
            output_path = os.path.join(out_folder, output_file)
            
            bit_pos = rand_bits[i]
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8
            
            bitflips[output_file] = {
                "original_file": file_path,
                "bit_position": bit_pos,
                "byte_index": byte_idx,
                "bit_index": bit_idx
            }
            
            with open(output_path, 'wb') as f:
                flipped = bytearray(data)
                
                # Flip the bit
                flipped[byte_idx] ^= (1 << bit_idx)
                
                f.write(flipped)
                
        return bitflips
    
    def save_bitflip_info(self, bitflips: Dict[str, Dict], output_path: str) -> None:
        """
        Save bit flip information to a JSON file.
        
        Parameters:
        -----------
        bitflips : Dict[str, Dict]
            Dictionary of bit flip information
        output_path : str
            Path to save the JSON file
        """
        with open(output_path, 'w') as f:
            json.dump(bitflips, f, indent=2)
            
    def inject_and_save(self, file_path: str, num_flips: int, out_folder: str, 
                        seed: Optional[int] = None) -> str:
        """
        Inject bitflips and save the bitflip information.
        
        Parameters:
        -----------
        file_path : str
            Path to the binary file to modify
        num_flips : int
            Number of bit flips to inject
        out_folder : str
            Directory to store the modified files
        seed : int, optional
            Random seed for reproducibility
            
        Returns:
        --------
        str
            Path to the JSON file containing bitflip information
        """
        bitflips = self.inject_bitflips(file_path, num_flips, out_folder, seed)
        
        json_filename = os.path.basename(file_path)[1:]
        parent_dir = os.path.dirname(out_folder.rstrip('/'))
        json_path = os.path.join(parent_dir, f"{json_filename}_bitflips.json")
        
        self.save_bitflip_info(bitflips, json_path)
        return json_path


def main():
    """Command line interface for the fault injecter."""
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python injecter.py <file> <num> <out_folder>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    num_flips = int(sys.argv[2])
    out_folder = sys.argv[3]
    
    injecter = FaultInjecter()
    injecter.inject_and_save(file_path, num_flips, out_folder)


if __name__ == "__main__":
    main()