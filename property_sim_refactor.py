
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import math
import pandas as pd
import numpy as np

# ------------------------------
# Helpers
# ------------------------------
def pct_to_dec(p: float) -> float:
    """Convert percent (eg 20 for 20 percent) to decimal (0.20)."""
    return float(p) / 100.0

def clamp_nonnegative(x: float) -> float:
    return max(0.0, float(x))

# ------------------------------
# Property Simulation
# ------------------------------
@dataclass
class PropertySim:
    # Required
    purchase_price: float
    down_payment_percent: float         # eg 20 for 20%
    annual_interest_percent: float      # eg 5.0 for 5%
    amort_years: int                    # eg 25

    # Rental type
    rental_type: str = "long_term"      # "long_term" or "short_term"

    # Revenue - Long-term rental
    monthly_rent: float = 0.0
    rent_growth_percent_per_year: float = 2.0
    vacancy_percent: float = 5.0

    # Revenue - Short-term rental
    nightly_rate: float = 0.0
    occupancy_percent: float = 65.0     # Average occupancy for STR
    cleaning_fee_per_stay: float = 100.0
    avg_stay_length_nights: float = 3.0
    platform_fee_percent: float = 15.0   # Airbnb/VRBO fees

    # Expenses - expressed as percents of price unless noted
    tax_percent_of_price_per_year: float = 1.2      # typical ballpark in many NS towns ~1.0-1.5%
    insurance_percent_of_price_per_year: float = 0.6
    maintenance_percent_of_price_per_year: float = 1.0
    other_costs_monthly: float = 0.0

    # Dynamics
    years: int = 20
    appreciation_percent_per_year: float = 3.0

    # Closing costs
    closing_costs_percent_of_price: float = 2.0

    # Meta
    start_date: str = "2025-01-01"

    # Internal fields (auto-populated)
    df: Optional[pd.DataFrame] = field(default=None, init=False)
    results: Dict[str, Any] = field(default_factory=dict, init=False)

    # ------------------------------
    # Derived values
    # ------------------------------
    @property
    def closing_costs(self) -> float:
        return self.purchase_price * pct_to_dec(self.closing_costs_percent_of_price)

    @property
    def down_payment(self) -> float:
        return self.purchase_price * pct_to_dec(self.down_payment_percent)

    @property
    def loan_amount(self) -> float:
        return clamp_nonnegative(self.purchase_price - self.down_payment)

    @property
    def total_upfront(self) -> float:
        return self.down_payment + self.closing_costs

    @property
    def tax_yearly(self) -> float:
        return self.purchase_price * pct_to_dec(self.tax_percent_of_price_per_year)

    @property
    def insurance_yearly(self) -> float:
        return self.purchase_price * pct_to_dec(self.insurance_percent_of_price_per_year)

    @property
    def maintenance_yearly(self) -> float:
        return self.purchase_price * pct_to_dec(self.maintenance_percent_of_price_per_year)

    @property
    def monthly_rate(self) -> float:
        return pct_to_dec(self.annual_interest_percent) / 12.0

    @property
    def total_months(self) -> int:
        return int(self.years * 12)

    def mortgage_payment_monthly(self, balance: Optional[float]=None) -> float:
        """Fixed-rate fully amortizing monthly payment (PMT)."""
        L = self.loan_amount if balance is None else balance
        r = self.monthly_rate
        n = self.amort_years * 12
        if r == 0:
            return L / n
        return L * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    # ------------------------------
    # Revenue calculation
    # ------------------------------
    def calculate_monthly_revenue(self, base_rate: float) -> float:
        """
        Calculate effective monthly revenue based on rental type.
        
        Args:
            base_rate: For long-term this is monthly_rent, for short-term this is nightly_rate
        
        Returns:
            Effective monthly revenue after vacancy/occupancy and fees
        """
        if self.rental_type == "short_term":
            # Short-term rental calculation
            days_per_month = 30.0
            occupied_days = days_per_month * pct_to_dec(self.occupancy_percent)
            num_stays = occupied_days / self.avg_stay_length_nights
            
            # Gross revenue = (nightly rate * occupied nights) + (cleaning fees * number of stays)
            gross_monthly = (base_rate * occupied_days) + (self.cleaning_fee_per_stay * num_stays)
            
            # Net after platform fees
            net_monthly = gross_monthly * (1 - pct_to_dec(self.platform_fee_percent))
            return net_monthly
        else:
            # Long-term rental calculation
            return base_rate * (1 - pct_to_dec(self.vacancy_percent))

    # ------------------------------
    # Cash-on-cash
    # ------------------------------
    def initial_cash_on_cash_percent(self) -> float:
        """NOI year 1 / total upfront."""
        if self.rental_type == "short_term":
            eff_rent_year1 = self.calculate_monthly_revenue(self.nightly_rate) * 12
        else:
            eff_rent_year1 = self.calculate_monthly_revenue(self.monthly_rent) * 12
        
        expenses_year1 = self.tax_yearly + self.insurance_yearly + self.maintenance_yearly + (self.other_costs_monthly * 12)
        # NOI is before debt service
        noi_year1 = eff_rent_year1 - expenses_year1
        return (noi_year1 / self.total_upfront) * 100.0

    # ------------------------------
    # Simulation
    # ------------------------------
    def run(self) -> pd.DataFrame:
        months = self.total_months
        current_price = float(self.purchase_price)
        balance = float(self.loan_amount)
        mmtg = self.mortgage_payment_monthly(balance=None)

        ts = []
        date = pd.Timestamp(self.start_date)

        monthly_tax = self.tax_yearly / 12.0
        monthly_ins = self.insurance_yearly / 12.0
        monthly_maint = self.maintenance_yearly / 12.0

        # Initialize base rate based on rental type
        if self.rental_type == "short_term":
            base_rate = float(self.nightly_rate)
        else:
            base_rate = float(self.monthly_rent)
        
        rent_growth = pct_to_dec(self.rent_growth_percent_per_year)
        appr = pct_to_dec(self.appreciation_percent_per_year)

        cumulative_cf = 0.0
        cumulative_principal = 0.0

        for m in range(months):
            # Annual bumps at the start of each new year after month 0
            if m > 0 and m % 12 == 0:
                base_rate *= (1 + rent_growth)
                current_price *= (1 + appr)
                monthly_tax = (current_price * pct_to_dec(self.tax_percent_of_price_per_year)) / 12.0
                monthly_ins = (current_price * pct_to_dec(self.insurance_percent_of_price_per_year)) / 12.0
                monthly_maint = (current_price * pct_to_dec(self.maintenance_percent_of_price_per_year)) / 12.0

            # Income - calculate based on rental type
            eff_rent = self.calculate_monthly_revenue(base_rate)

            # Mortgage split
            interest = balance * self.monthly_rate
            principal = min(mmtg - interest, balance)  # avoid negative balance
            principal = clamp_nonnegative(principal)
            balance = clamp_nonnegative(balance - principal)

            # Expenses
            expenses = monthly_tax + monthly_ins + monthly_maint + self.other_costs_monthly

            # Cash flow after debt service
            monthly_cf = eff_rent - expenses - mmtg
            cumulative_cf += monthly_cf
            cumulative_principal += principal

            ts.append({
                "date": date,
                "month_index": m,
                "effective_rent": eff_rent,
                "expenses": expenses,
                "mortgage_payment": mmtg,
                "interest": interest,
                "principal": principal,
                "balance": balance,
                "monthly_cash_flow": monthly_cf,
                "cumulative_cash_flow": cumulative_cf,
                "property_value": current_price,
            })

            date = date + pd.DateOffset(months=1)

            if balance <= 0.0:
                # After payoff: mortgage payment becomes 0, cash flow jumps
                # We still continue the sim horizon to show post-payoff CF
                mmtg = 0.0

        df = pd.DataFrame(ts)
        self.df = df

        # Basic summary metrics
        upfront = self.total_upfront
        # At each month, total cash invested so far is upfront + any negative cumulative CF up to that month
        neg_cf = min(0.0, cumulative_cf)  # if CF went negative overall
        total_invested = upfront + abs(neg_cf)

        terminal_equity = current_price - balance
        # Value growth is current_price - purchase_price
        # Total return approximation: equity built + cumulative CF
        total_return = terminal_equity - (self.purchase_price - self.down_payment) + cumulative_cf

        # Break-even: when cumulative CF crosses zero vs upfront is a common view.
        # We track when cumulative CF equals upfront (payback)
        payback_month = None
        if df["cumulative_cash_flow"].iloc[0] >= 0:
            # If immediately positive, payback month is 0
            payback_month = 0
        else:
            # Find first index where cumulative CF >= upfront *or* crosses 0, pick the upfront payback
            # Here we choose payback on upfront: cumulative_CF >= total_upfront
            crossed = np.where(df["cumulative_cash_flow"].values >= upfront)[0]
            payback_month = int(crossed[0]) if len(crossed) > 0 else None

        self.results = {
            "monthly_mortgage": self.mortgage_payment_monthly(),
            "initial_cash_on_cash_percent": self.initial_cash_on_cash_percent(),
            "ending_monthly_cash_flow": float(df["monthly_cash_flow"].iloc[-1]),
            "cumulative_cash_flow": float(cumulative_cf),
            "terminal_equity": float(terminal_equity),
            "total_invested_est": float(total_invested),
            "total_return_est": float(total_return),
            "payback_month_on_upfront": payback_month,
        }
        return df

    def kpis(self) -> Dict[str, Any]:
        if not self.results:
            self.run()
        return self.results
