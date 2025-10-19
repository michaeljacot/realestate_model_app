"""
Auto-simulation utilities for PropertySim.

This module provides tools to run multiple simulations with varying parameters
to find optimal values, such as the minimum down payment for positive cash flow.
"""

import pandas as pd
import numpy as np
from dataclasses import replace
from property_sim_refactor import PropertySim


class AutoSim:
    """
    Wrapper around PropertySim to run multiple simulations with varying parameters.
    """

    def __init__(self, base_sim: PropertySim):
        """
        Initialize with a base PropertySim configuration.
        
        Args:
            base_sim: The base PropertySim object to use as a template
        """
        self.base_sim = base_sim

    def down_payment_for_cashflow(
        self, 
        upper_limit: float = 50.0, 
        lower_limit: float = 5.0, 
        num_simulations: int = 25,
        progress_callback=None
    ) -> tuple[pd.DataFrame, float | None, float | None]:
        """
        Find the minimum down payment percentage that results in positive monthly cash flow.
        
        This method runs multiple simulations with different down payment percentages
        to find the break-even point where monthly cash flow becomes positive.
        
        Args:
            upper_limit: Maximum down payment percentage to test (default 50%)
            lower_limit: Minimum down payment percentage to test (default 5%)
            num_simulations: Number of simulations to run (default 25)
            progress_callback: Optional callback function(current_index, total, current_result_dict)
            
        Returns:
            tuple containing:
                - DataFrame with all simulation results
                - Dollar amount of down payment that achieves positive cash flow (or None)
                - Percentage that achieves positive cash flow (or None)
        """
        # Create a range of down payment percentages to test
        down_payment_range = np.linspace(lower_limit, upper_limit, num_simulations)
        
        # Store results
        results = []
        
        # Run simulations for each down payment percentage
        for idx, down_payment_percent in enumerate(down_payment_range):
            # Create a new sim with this down payment percentage
            sim = replace(self.base_sim, down_payment_percent=down_payment_percent)
            
            # Run the simulation
            df = sim.run()
            kpis = sim.kpis()
            
            # Get the first month's cash flow (initial monthly cash flow)
            monthly_cashflow = df['monthly_cash_flow'].iloc[0]
            
            # Get the down payment dollar amount
            down_payment = sim.down_payment
            
            # Get other key metrics from the first month
            effective_rent = df['effective_rent'].iloc[0]
            monthly_expenses = df['expenses'].iloc[0]
            monthly_mortgage = df['mortgage_payment'].iloc[0]
            
            # Store the results
            result_dict = {
                'down_payment_percentage': down_payment_percent,
                'down_payment': down_payment,
                'monthly_cash_flow': monthly_cashflow,
                'effective_rent': effective_rent,
                'monthly_expenses': monthly_expenses,
                'monthly_mortgage': monthly_mortgage,
                'initial_coc_percent': kpis['initial_cash_on_cash_percent'],
                'cumulative_cf': kpis['cumulative_cash_flow'],
                'terminal_equity': kpis['terminal_equity'],
            }
            results.append(result_dict)
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(idx + 1, num_simulations, result_dict)
            
            # Early exit: stop if we found positive cash flow
            if monthly_cashflow > 0:
                break
        
        # Convert to DataFrame
        results_df = pd.DataFrame(results)
        
        # Find the first down payment that results in positive monthly cash flow
        positive_cf = results_df[results_df['monthly_cash_flow'] > 0]
        
        if not positive_cf.empty:
            down_payment_cashflow = float(positive_cf['down_payment'].iloc[0])
            down_payment_percent_cashflow = float(positive_cf['down_payment_percentage'].iloc[0])
        else:
            down_payment_cashflow = None
            down_payment_percent_cashflow = None
        
        return results_df, down_payment_cashflow, down_payment_percent_cashflow


def create_down_payment_plot(df: pd.DataFrame, save_path: str | None = None) -> None:
    """
    Create a visualization of monthly cash flow and mortgage vs down payment percentage.
    
    Args:
        df: DataFrame from down_payment_for_cashflow() method
        save_path: Optional path to save the plot image
    """
    import matplotlib.pyplot as plt
    
    # Create the plot
    plt.figure(figsize=(12, 8))
    plt.plot(
        df['down_payment_percentage'], 
        df['monthly_cash_flow'], 
        label='Monthly Cash Flow', 
        marker='o', 
        color='#1f77b4', 
        markersize=8,
        linewidth=2
    )
    plt.plot(
        df['down_payment_percentage'], 
        df['monthly_mortgage'], 
        label='Monthly Mortgage', 
        marker='v', 
        color='#8c564b', 
        markersize=8,
        linewidth=2
    )
    
    # Find and mark the break-even point (where cash flow crosses zero)
    zero_crossings = df[df['monthly_cash_flow'] * df['monthly_cash_flow'].shift(1) <= 0]
    
    if not zero_crossings.empty:
        for _, row in zero_crossings.iterrows():
            break_even_text = (
                f'Break-Even Cash Flow\n'
                f'{row["down_payment_percentage"]:.2f}%\n'
                f'${row["down_payment"]:,.0f}'
            )
            break_even_coords = (row['down_payment_percentage'], row['monthly_cash_flow'])
            
            # Mark the break-even point
            plt.plot(
                row['down_payment_percentage'], 
                row['monthly_cash_flow'], 
                'ro', 
                markersize=12,
                label='Break-Even'
            )
            
            # Add annotation
            plt.annotate(
                break_even_text,
                xy=break_even_coords,
                xytext=(10, 20),
                textcoords='offset points',
                fontsize=10,
                bbox=dict(facecolor='white', edgecolor='green', boxstyle='round,pad=0.5'),
                arrowprops=dict(arrowstyle='->', color='green', lw=2)
            )
    
    # Add horizontal line at y=0
    plt.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.7)
    
    # Customize x-axis to show both percentage and dollar amount
    num_ticks = min(8, len(df))
    if num_ticks > 1:
        tick_indices = np.linspace(0, len(df) - 1, num_ticks, dtype=int)
        tick_labels = [
            f'{df["down_payment_percentage"].iloc[i]:.1f}%\n${df["down_payment"].iloc[i]:,.0f}'
            for i in tick_indices
        ]
        plt.xticks(
            df['down_payment_percentage'].iloc[tick_indices], 
            tick_labels, 
            rotation=45, 
            ha='right',
            fontsize=10
        )
    
    # Format y-axis as currency
    ax = plt.gca()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    plt.yticks(fontsize=10)
    
    # Labels and title
    plt.xlabel('Down Payment (% and Amount)', fontsize=12, fontweight='bold')
    plt.ylabel('Monthly Amount ($)', fontsize=12, fontweight='bold')
    plt.title('Property Simulation: Cash Flow vs Down Payment', fontsize=14, fontweight='bold')
    plt.legend(fontsize=11, loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save or show
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {save_path}")
    else:
        plt.show()
    
    plt.close()
