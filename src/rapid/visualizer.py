import os
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import Patch
import math

class ResultsVisualizer:
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
    
    @staticmethod
    def _format_k_ticks(x, pos):
        """Format x-axis ticks in thousands (k)"""
        return f"{int(x/1000)}k"
    
    def __init__(self, output_dir="plots"):
        """Initialize visualizer with output directory"""
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def plot_trap_causes_comparison(self, benchmark_analyzers, output_dir=None, top_n=5):
        """Create a grouped bar chart comparing top trap causes across multiple benchmarks
        
        Parameters:
        -----------
        benchmark_analyzers : dict
            Dictionary mapping benchmark names to ResultsAnalyzer objects
        output_dir : str, optional
            Directory to save the plot (defaults to self.output_dir if None)
        top_n : int, optional
            Number of top trap causes to display for each benchmark (default: 5)
        """
        if output_dir is None:
            output_dir = self.output_dir
        
        # Get trap causes for all benchmarks
        benchmark_trap_data = {}
        
        for name, analyzer in benchmark_analyzers.items():
            trap_causes = analyzer.count_by_trap_cause()
            if trap_causes:
                sorted_causes = sorted(trap_causes.items(), key=lambda x: x[1], reverse=True)
                top_causes = dict(sorted_causes[:4])
                
                if len(sorted_causes) > 4:
                    other_count = sum(count for _, count in sorted_causes[4:])
                    if other_count > 0:
                        top_causes["Others"] = other_count
                
                benchmark_trap_data[name] = top_causes
        
        if not benchmark_trap_data:
            print("No trap data available for any benchmark")
            return
        
        hatch_patterns = ['', '/', '\\', 'x', '-', '+', 'o', 'O', '.', 'x']
        
        for benchmark, trap_causes in benchmark_trap_data.items():
            if not trap_causes:
                continue
                
            causes_sorted = sorted(trap_causes.items(), key=lambda x: x[1], reverse=True)
            if "Others" in trap_causes:
                causes_sorted = [item for item in causes_sorted if item[0] != "Others"]
                causes_sorted.append(("Others", trap_causes["Others"]))
            
            causes = [cause for cause, _ in causes_sorted]
            counts = [count for _, count in causes_sorted]
            total = sum(counts)
            percentages = [(count / total) * 100 for count in counts]
            
            plt.figure(figsize=(12, 7))
            bar_colors = ['#9b59b6' if cause != "Others" else '#95a5a6' for cause in causes]
            bars = plt.bar(range(len(causes)), percentages, color=bar_colors, alpha=0.8)
            for i, (bar, count) in enumerate(zip(bars, counts)):
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                        f'{count} ({percentages[i]:.1f}%)',
                        ha='center', va='bottom', fontsize=9)
            
            plt.title(f'Top Trap Causes for {benchmark}', fontsize=16)
            plt.ylabel('Percentage of Traps (%)', fontsize=14)
            plt.xlabel('Trap Cause', fontsize=14)
            plt.xticks(range(len(causes)), causes, rotation=45, ha='right')
            plt.grid(axis='y', linestyle='--', alpha=0.5)
            plt.text(0.02, 0.95, f'Total Traps: {total}', 
                    transform=plt.gca().transAxes, fontsize=12,
                    bbox=dict(boxstyle='round,pad=0.5', fc='white', alpha=0.8))
            plt.tight_layout()
            
            output_file = os.path.join(output_dir, f"{benchmark}_trap_causes.png")
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"Trap causes chart for {benchmark} saved to {output_file}")
            plt.close()
        
        if len(benchmark_trap_data) > 1:
            plt.figure(figsize=(14, 8))
            
            num_benchmarks = len(benchmark_trap_data)
            columns_per_benchmark = 5
            total_width = 0.7
            group_width = total_width / num_benchmarks
            bar_width = group_width / columns_per_benchmark * 0.7
            
            all_positions = []
            all_labels = []
            current_x = 0
            
            benchmark_colors = [plt.cm.tab10(i % 10) for i in range(num_benchmarks)]
            
            for i, (benchmark, trap_causes) in enumerate(benchmark_trap_data.items()):
                sorted_causes = sorted(trap_causes.items(), key=lambda x: x[1], reverse=True)
                if "Others" in trap_causes:
                    sorted_causes = [item for item in sorted_causes if item[0] != "Others"]
                    sorted_causes.append(("Others", trap_causes["Others"]))
                
                causes = [cause for cause, _ in sorted_causes]
                counts = [count for _, count in sorted_causes]
                
                while len(causes) < 5:
                    causes.append("")
                    counts.append(0)
                    
                total = sum([c for c in counts if c > 0])
                percentages = [(count / total) * 100 if total > 0 and count > 0 else 0 for count in counts]
                positions = [current_x + j * bar_width * 1.2 for j in range(len(causes))]
                
                for pos, label in zip(positions, causes):
                    all_positions.append(pos)
                    all_labels.append(label)
                
                benchmark_color = benchmark_colors[i]
                for j, (position, percentage, cause) in enumerate(zip(positions, percentages, causes)):
                    if percentage > 0:
                        bar = plt.bar(position, percentage, width=bar_width, 
                                  color=benchmark_color, 
                                  alpha=0.7,
                                  edgecolor='black',
                                  linewidth=1)
                        
                        if j < len(hatch_patterns):
                            bar[0].set_hatch(hatch_patterns[j] * 2)
                
                for j, (position, percentage, count) in enumerate(zip(positions, percentages, counts)):
                    if count > 0:
                        plt.text(position, percentage + 1,
                                f'{percentage:.1f}%',
                                ha='center', va='bottom', fontsize=8,
                                color='black')
                
                if i < num_benchmarks - 1:
                    plt.axvline(x=positions[-1] + bar_width * 1.5, 
                              color='black', linestyle='-', alpha=0.3)
                
                current_x = positions[-1] + bar_width * 3
            
            plt.xticks(all_positions, all_labels, rotation=45, ha='right', fontsize=9, color='black')
            
            current_x = 0
            for i, benchmark in enumerate(benchmark_trap_data.keys()):
                positions = [current_x + j * bar_width * 1.2 for j in range(5)]
                mid_x = (positions[0] + positions[-1]) / 2
                plt.text(mid_x, -8, benchmark, ha='center', va='top', fontsize=11,
                       fontweight='bold', color='black')
                current_x = positions[-1] + bar_width * 3
            
            plt.ylabel('Percentage of Traps (%)', fontsize=14, color='black')
            plt.title('Top Trap Causes by Benchmark', fontsize=16, color='black')
            plt.grid(axis='y', linestyle='--', alpha=0.7)

            y_offset = 0.05
            for i, (benchmark, causes) in enumerate(benchmark_trap_data.items()):
                total = sum(causes.values())
                plt.annotate(f'{benchmark}: {total} traps', 
                            xy=(0.02, 0.95 - i*y_offset), 
                            xycoords='axes fraction',
                            fontsize=10,
                            color='black',
                            bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8, 
                                     ec='black'))
            
            plt.tight_layout()
            
            output_file = os.path.join(output_dir, f"trap_causes_comparison.png")
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"Combined trap causes comparison chart saved to {output_file}")
            plt.close()

    def plot_bit_position_impact(self, bit_position_stats, benchmark_name, num_chunks=30):
        """Create a line chart showing the impact of bit position on test outcomes
        
        Parameters:
        -----------
        bit_position_stats : dict
            Dictionary containing bit position data by status type
        benchmark_name : str
            Name of the benchmark for plot title
        num_chunks : int, default=30
            Number of chunks to divide the bit positions into
        """
        if not any(bit_position_stats.values()):
            print("No bit position data available for plotting")
            return
        
        plt.figure(figsize=(14, 8))
                
        max_bit_pos = 0
        min_bit_pos = float('inf')
        for positions in bit_position_stats.values():
            if positions:
                max_bit_pos = max(max_bit_pos, max(positions.keys() or [0]))
                min_bit_pos = min(min_bit_pos, min(positions.keys() or [float('inf')]))
        
        if min_bit_pos == float('inf'):
            min_bit_pos = 0
        
        bit_range = max_bit_pos - min_bit_pos + 1
        chunk_size = max(1, bit_range // num_chunks)
        num_chunks = math.ceil(bit_range / chunk_size)
        
        chunk_data = {status_type: [0] * num_chunks for status_type in bit_position_stats.keys()}
        
        for status_type, positions in bit_position_stats.items():
            for bit_pos, count in positions.items():
                chunk_idx = (bit_pos - min_bit_pos) // chunk_size
                if 0 <= chunk_idx < num_chunks:
                    chunk_data[status_type][chunk_idx] += count
        
        x_points = [min_bit_pos + (i * chunk_size) + chunk_size/2 for i in range(num_chunks)]
        
        for status_type, counts in chunk_data.items():
            if sum(counts) > 0:
                plt.plot(
                    x_points, 
                    counts, 
                    label=status_type.capitalize(),
                    linestyle=self.LINE_STYLES.get(status_type, '-'),
                    color=self.STATUS_COLORS.get(status_type, 'black'),
                    linewidth=2, 
                    marker='o',
                    markersize=4
                )
        
        plt.xlabel('Bit Position', fontsize=14)
        plt.ylabel('Count', fontsize=14)
        plt.title(f'Impact of Bit Position on Test Outcomes for {benchmark_name}', fontsize=16)
        plt.gca().xaxis.set_major_formatter(FuncFormatter(self._format_k_ticks))
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend(loc='upper right', fontsize=12)
        plt.text(0.02, 0.98, f"Chunk size: {chunk_size} bits", 
                transform=plt.gca().transAxes, fontsize=10, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        output_file = os.path.join(self.output_dir, f"{benchmark_name}_bit_position_impact.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Bit position impact chart saved to {output_file}")
        plt.close()
    
    def plot_status_hierarchy_bars(self, counts, total_tests, benchmark_name):
        """Create a bar chart showing hierarchical status categories and their combinations"""
        if total_tests == 0:
            print("No test data available for plotting")
            return
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        main_bar_width = 0.5
        sub_bar_width = main_bar_width / 5
        index = np.arange(3)
        
        main_categories = ["passed", "failed", "outlier"]
        main_totals = [counts[cat]["total"] for cat in main_categories]
        main_colors = [self.STATUS_COLORS.get(cat, '#888888') for cat in main_categories]
        
        main_bars = ax.bar(index, main_totals, main_bar_width, 
                        color=main_colors, label="Total", alpha=0.8)
        
        subcategories = {
            "passed": ["clean", "trap", "SDC"],
            "failed": ["clean", "trap", "halt", "comm_failure"],
            "outlier": ["trap", "halt", "comm_failure"]
        }
        
        for i, main_cat in enumerate(main_categories):
            subcats = subcategories[main_cat]
            for j, subcat in enumerate(subcats):
                pos = index[i] - main_bar_width/2 + (j+0.5)*sub_bar_width
                count = counts[main_cat][subcat]
                if count > 0:
                    ax.bar(pos, count, sub_bar_width, 
                        color=self.SUBCAT_COLORS.get(subcat, '#888888'),
                        label=f"{main_cat}:{subcat}" if i == 0 else "_nolegend_")
        
        for bar in main_bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height + 5,
                    f"{int(height)}", ha='center', va='bottom', fontweight='bold')
        
        y_max = max(main_totals) * 1.15
        ax.set_ylim(0, y_max)
        
        legend_elements = [
            Patch(facecolor=self.STATUS_COLORS["passed"], alpha=0.7, label="Passed (Total)"),
            Patch(facecolor=self.SUBCAT_COLORS["clean"], label="Passed - Clean"),
            Patch(facecolor=self.SUBCAT_COLORS["trap"], label="Passed - With Trap"),
            Patch(facecolor=self.SUBCAT_COLORS["SDC"], label="Passed - SDC"),
            
            Patch(facecolor='none', label=''),  # Empty spacer
            
            Patch(facecolor=self.STATUS_COLORS["failed"], alpha=0.7, label="Failed (Total)"),
            Patch(facecolor=self.SUBCAT_COLORS["clean"], label="Failed - Clean"),
            Patch(facecolor=self.SUBCAT_COLORS["trap"], label="Failed - With Trap"),
            Patch(facecolor=self.SUBCAT_COLORS["halt"], label="Failed - Halt"),
            Patch(facecolor=self.SUBCAT_COLORS["comm_failure"], label="Failed - Communication Failure"),
            Patch(facecolor=self.SUBCAT_COLORS["other"], label="Failed - Multiple Issues"),
            
            Patch(facecolor='none', label=''),  # Empty spacer
            
            Patch(facecolor=self.STATUS_COLORS["outlier"], alpha=0.7, label="Outlier (Total)"),
            Patch(facecolor=self.SUBCAT_COLORS["trap"], label="Outlier - With Trap"),
            Patch(facecolor=self.SUBCAT_COLORS["halt"], label="Outlier - Halt"),
            Patch(facecolor=self.SUBCAT_COLORS["comm_failure"], label="Outlier - Communication Failure")
        ]

        ax.legend(handles=legend_elements, loc='upper right', fontsize=10, ncol=1)
        
        ax.set_title(f'Status Distribution by Category for {benchmark_name}', fontsize=16)
        ax.set_ylabel('Number of Tests', fontsize=14)
        ax.set_xticks(index)
        ax.set_xticklabels(['Passed', 'Failed', 'Outlier'], fontsize=14)
        ax.grid(True, axis='y', linestyle='--', alpha=0.3)
        plt.text(0.02, 0.98, f"Total Tests: {total_tests}", 
                transform=ax.transAxes, fontsize=12, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        plt.tight_layout()
        
        output_file = os.path.join(self.output_dir, f"{benchmark_name}_status_bars.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Status hierarchy bar chart saved to {output_file}")
        plt.close()