
import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import json
from pathlib import Path
from property_sim_refactor import PropertySim
from auto_sim import AutoSim, create_down_payment_plot
import sim_db

DB_PATH = str(Path(__file__).resolve().parent / "simdb.sqlite")
sim_db.init_db(DB_PATH)

st.set_page_config(page_title="Property Simulator", layout="wide")
st.title("Property Investment Simulator")

# Session helpers
if "selected_property_id" not in st.session_state:
    st.session_state.selected_property_id = None
if "selected_scenario_id" not in st.session_state:
    st.session_state.selected_scenario_id = None

# -------------------------
# Left column: Property + Scenario selectors
# -------------------------
c_left, c_right = st.columns([1, 2])

with c_left:
    st.subheader("Property")
    props = sim_db.list_properties(DB_PATH)
    prop_options = ["New property"] + [f"{p['id']}: {p.get('address') or '(no address)'}" for p in props]
    prop_choice = st.selectbox("Select property", prop_options, index=0)

    # Build a form for property
    if prop_choice == "New property":
        prop_data = {
            "id": None,
            "address": "",
            "mls_number": "",
            "latitude": None,
            "longitude": None,
            "beds": None,
            "baths": None,
            "sqft": None,
            "year_built": None,
            "notes": "",
            "purchase_price": None,
            "down_payment_percent": None,
            "annual_interest_percent": None,
            "amort_years": None,
            "closing_costs_percent_of_price": None,
        }
    else:
        sel_id = int(prop_choice.split(":")[0])
        st.session_state.selected_property_id = sel_id
        prop_data = next(p for p in props if p["id"] == sel_id)

    with st.form("prop_form"):
        address = st.text_input("Address", value=prop_data.get("address") or "")
        mls = st.text_input("MLS number", value=prop_data.get("mls_number") or "")
        colA, colB = st.columns(2)
        with colA:
            lat = st.number_input("Latitude", value=float(prop_data.get("latitude") or 0.0), format="%.6f")
            beds = st.number_input("Beds", value=int(prop_data.get("beds") or 0), step=1)
            sqft = st.number_input("Square footage", value=int(prop_data.get("sqft") or 0), step=50)
        with colB:
            lon = st.number_input("Longitude", value=float(prop_data.get("longitude") or 0.0), format="%.6f")
            baths = st.number_input("Baths", value=int(prop_data.get("baths") or 0), step=1)
            year_built = st.number_input("Year built", value=int(prop_data.get("year_built") or 1980), step=1, min_value=1800, max_value=2100)
        notes = st.text_area("Notes", value=prop_data.get("notes") or "", height=100)

        st.markdown("---")
        st.subheader("Purchase details")
        purchase_price = st.number_input(
            "Purchase price ($)",
            min_value=10000.0,
            value=float(prop_data.get("purchase_price") or 300000.0),
            step=1000.0,
        )
        down_pct = st.slider(
            "Down payment (%)",
            0.0,
            100.0,
            float(prop_data.get("down_payment_percent") if prop_data.get("down_payment_percent") is not None else 20.0),
            0.5,
        )
        rate_pct = st.slider(
            "Interest rate - annual (%)",
            0.0,
            20.0,
            float(prop_data.get("annual_interest_percent") if prop_data.get("annual_interest_percent") is not None else 5.0),
            0.1,
        )
        amort_years = st.slider(
            "Amortization (years)",
            1,
            35,
            int(prop_data.get("amort_years") if prop_data.get("amort_years") is not None else 25),
            1,
        )
        closing_pct = st.slider(
            "Closing costs (%)",
            0.0,
            10.0,
            float(prop_data.get("closing_costs_percent_of_price") if prop_data.get("closing_costs_percent_of_price") is not None else 2.0),
            0.5,
        )
        submitted_prop = st.form_submit_button("Save property")
        if submitted_prop:
            up = {
                "id": prop_data.get("id"),
                "address": address or None,
                "mls_number": mls or None,
                "latitude": lat if lat != 0.0 else None,
                "longitude": lon if lon != 0.0 else None,
                "beds": beds or None,
                "baths": baths or None,
                "sqft": sqft or None,
                "year_built": year_built or None,
                "notes": notes or None,
                "purchase_price": purchase_price,
                "down_payment_percent": down_pct,
                "annual_interest_percent": rate_pct,
                "amort_years": amort_years,
                "closing_costs_percent_of_price": closing_pct,
            }
            new_id = sim_db.upsert_property(up, DB_PATH)
            st.success(f"Property saved (id {new_id}).")
            st.session_state.selected_property_id = new_id

    if st.session_state.selected_property_id:
        with st.expander("Danger zone"):
            if st.button("Delete property"):
                sim_db.delete_property(st.session_state.selected_property_id, DB_PATH)
                st.session_state.selected_property_id = None
                st.session_state.selected_scenario_id = None
                st.warning("Property deleted.")

    st.markdown("---")
    st.subheader("Income Scenario")
    if st.session_state.selected_property_id is None:
        st.info("Save a property to create income scenarios.")
    else:
        prop_record = sim_db.get_property(st.session_state.selected_property_id, DB_PATH)
        required_purchase_fields = [
            "purchase_price",
            "down_payment_percent",
            "annual_interest_percent",
            "amort_years",
            "closing_costs_percent_of_price",
        ]
        if not prop_record:
            st.error("Property could not be loaded. Please refresh and try again.")
        elif any(prop_record.get(k) is None for k in required_purchase_fields):
            st.info("Add purchase details to the property before creating income scenarios.")
        else:
            purchase_details = {k: prop_record.get(k) for k in required_purchase_fields}
            scenarios = sim_db.list_scenarios(st.session_state.selected_property_id, DB_PATH)
            scen_options = ["New scenario"] + [f"{s['id']}: {s['name']}" for s in scenarios]

            # Find the index of the currently selected scenario
            default_index = 0
            if st.session_state.selected_scenario_id is not None:
                for i, opt in enumerate(scen_options):
                    if opt != "New scenario" and int(opt.split(":")[0]) == st.session_state.selected_scenario_id:
                        default_index = i
                        break

            scen_choice = st.selectbox("Select scenario", scen_options, index=default_index)

            if scen_choice == "New scenario":
                st.session_state.selected_scenario_id = None
                scen_name = st.text_input("Scenario name", value="Base case")
                params = {}
            else:
                scen_id = int(scen_choice.split(":")[0])
                st.session_state.selected_scenario_id = scen_id
                rec = sim_db.get_scenario(scen_id, DB_PATH)
                scen_name = st.text_input("Scenario name", value=rec["name"])
                params = rec.get("params") or {}

            # Scenario param form
            def getp(k, default):
                return params.get(k, default)

            # Rental type selection - OUTSIDE the form so it updates immediately
            rental_type = st.radio(
                "Rental Type",
                options=["long_term", "short_term"],
                format_func=lambda x: "Long-term Rental" if x == "long_term" else "Short-term Rental (Airbnb/VRBO)",
                index=0 if getp("rental_type", "long_term") == "long_term" else 1,
                horizontal=True,
                key="rental_type_selector"
            )

            with st.form("scenario_form"):
                st.caption("Define income and expense assumptions. These are saved to SQLite.")

                st.markdown("---")
                st.subheader("Revenue")

                # Conditional inputs based on rental type
                if rental_type == "long_term":
                    monthly_rent = st.number_input("Monthly rent ($)", min_value=0.0, value=float(getp("monthly_rent", 2200.0)), step=50.0)
                    rent_growth_pct = st.slider("Rent growth per year (%)", 0.0, 15.0, float(getp("rent_growth_percent_per_year", 2.0)), 0.5)
                    vacancy_pct = st.slider("Vacancy (%)", 0.0, 30.0, float(getp("vacancy_percent", 5.0)), 0.5)

                    # Set short-term values to 0
                    nightly_rate = 0.0
                    occupancy_pct = 65.0
                    cleaning_fee = 100.0
                    avg_stay = 3.0
                    platform_fee = 15.0
                else:
                    nightly_rate = st.number_input("Nightly rate ($)", min_value=0.0, value=float(getp("nightly_rate", 150.0)), step=10.0)
                    occupancy_pct = st.slider("Occupancy rate (%)", 0.0, 100.0, float(getp("occupancy_percent", 65.0)), 1.0)
                    cleaning_fee = st.number_input("Cleaning fee per stay ($)", min_value=0.0, value=float(getp("cleaning_fee_per_stay", 100.0)), step=10.0)
                    avg_stay = st.number_input("Average stay length (nights)", min_value=1.0, value=float(getp("avg_stay_length_nights", 3.0)), step=0.5)
                    platform_fee = st.slider("Platform fees (%)", 0.0, 30.0, float(getp("platform_fee_percent", 15.0)), 0.5)
                    rent_growth_pct = st.slider("Rate growth per year (%)", 0.0, 15.0, float(getp("rent_growth_percent_per_year", 3.0)), 0.5)

                    # Set long-term values to 0
                    monthly_rent = 0.0
                    vacancy_pct = 0.0

                st.markdown("---")
                st.subheader("Annual expense rates - % of price")
                tax_pct = st.slider("Property tax (%)", 0.0, 3.0, float(getp("tax_percent_of_price_per_year", 1.2)), 0.1)
                ins_pct = st.slider("Insurance (%)", 0.0, 3.0, float(getp("insurance_percent_of_price_per_year", 0.6)), 0.1)
                maint_pct = st.slider("Maintenance (%)", 0.0, 4.0, float(getp("maintenance_percent_of_price_per_year", 1.0)), 0.1)
                other_monthly = st.number_input("Other monthly costs ($)", min_value=0.0, value=float(getp("other_costs_monthly", 0.0)), step=25.0)

                st.markdown("---")
                st.subheader("Market assumptions")
                yrs = st.slider("Simulation horizon (years)", 1, 40, int(getp("years", 20)), 1)
                appr_pct = st.slider("Appreciation per year (%)", 0.0, 10.0, float(getp("appreciation_percent_per_year", 3.0)), 0.5)

                form_saved = st.form_submit_button("Save Income Scenario")
                if form_saved:
                    # Merge purchase details with scenario params
                    param_dict = {
                        **purchase_details,
                        "rental_type": rental_type,
                        "monthly_rent": monthly_rent,
                        "rent_growth_percent_per_year": rent_growth_pct,
                        "vacancy_percent": vacancy_pct,
                        "nightly_rate": nightly_rate,
                        "occupancy_percent": occupancy_pct,
                        "cleaning_fee_per_stay": cleaning_fee,
                        "avg_stay_length_nights": avg_stay,
                        "platform_fee_percent": platform_fee,
                        "tax_percent_of_price_per_year": tax_pct,
                        "insurance_percent_of_price_per_year": ins_pct,
                        "maintenance_percent_of_price_per_year": maint_pct,
                        "other_costs_monthly": other_monthly,
                        "years": yrs,
                        "appreciation_percent_per_year": appr_pct,
                    }
                    if st.session_state.selected_scenario_id is None:
                        new_id = sim_db.create_scenario(
                            property_id=st.session_state.selected_property_id,
                            name=scen_name or "Scenario",
                            params=param_dict,
                            db_path=DB_PATH,
                        )
                        st.session_state.selected_scenario_id = new_id
                        st.success(f"Income scenario created (id {new_id}).")
                    else:
                        sim_db.update_scenario(
                            scenario_id=st.session_state.selected_scenario_id,
                            name=scen_name or "Scenario",
                            params=param_dict,
                            db_path=DB_PATH,
                        )
                        st.success("Income scenario updated.")

        if st.session_state.selected_scenario_id:
            cc1, cc2, cc3 = st.columns(3)
            if cc1.button("Duplicate income scenario"):
                rec = sim_db.get_scenario(st.session_state.selected_scenario_id, DB_PATH)
                new_id = sim_db.create_scenario(
                    property_id=rec["property_id"],
                    name=(rec["name"] + " copy")[:100],
                    params=rec["params"],
                    db_path=DB_PATH,
                )
                st.success(f"Income scenario duplicated as id {new_id}.")
            if cc2.button("Delete income scenario"):
                sim_db.delete_scenario(st.session_state.selected_scenario_id, DB_PATH)
                st.session_state.selected_scenario_id = None
                st.warning("Income scenario deleted.")

with c_right:
    st.subheader("Run and visualize")
    if not st.session_state.selected_scenario_id:
        st.info("Select and save an income scenario to run the simulation.")
    else:
        rec = sim_db.get_scenario(st.session_state.selected_scenario_id, DB_PATH)
        p = rec["params"]

        # Build the model from saved params
        sim = PropertySim(
            purchase_price=p["purchase_price"],
            down_payment_percent=p["down_payment_percent"],
            annual_interest_percent=p["annual_interest_percent"],
            amort_years=p["amort_years"],
            rental_type=p.get("rental_type", "long_term"),
            monthly_rent=p.get("monthly_rent", 0.0),
            rent_growth_percent_per_year=p["rent_growth_percent_per_year"],
            vacancy_percent=p.get("vacancy_percent", 5.0),
            nightly_rate=p.get("nightly_rate", 0.0),
            occupancy_percent=p.get("occupancy_percent", 65.0),
            cleaning_fee_per_stay=p.get("cleaning_fee_per_stay", 100.0),
            avg_stay_length_nights=p.get("avg_stay_length_nights", 3.0),
            platform_fee_percent=p.get("platform_fee_percent", 15.0),
            tax_percent_of_price_per_year=p["tax_percent_of_price_per_year"],
            insurance_percent_of_price_per_year=p["insurance_percent_of_price_per_year"],
            maintenance_percent_of_price_per_year=p["maintenance_percent_of_price_per_year"],
            other_costs_monthly=p["other_costs_monthly"],
            years=p["years"],
            appreciation_percent_per_year=p["appreciation_percent_per_year"],
            closing_costs_percent_of_price=p["closing_costs_percent_of_price"],
        )

        if st.button("Run simulation"):
            df = sim.run()
            k = sim.kpis()

            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Monthly mortgage", f"${k['monthly_mortgage']:,.0f}")
            c2.metric("Initial CoC", f"{k['initial_cash_on_cash_percent']:.1f}%")
            c3.metric("Ending monthly CF", f"${k['ending_monthly_cash_flow']:,.0f}")
            c4.metric("Payback month", k['payback_month_on_upfront'] if k['payback_month_on_upfront'] is not None else "Not reached")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Cumulative CF", f"${k['cumulative_cash_flow']:,.0f}")
            c6.metric("Terminal equity", f"${k['terminal_equity']:,.0f}")
            c7.metric("Total invested", f"${k['total_invested_est']:,.0f}")
            c8.metric("Total return", f"${k['total_return_est']:,.0f}")

            # Plots
            st.subheader("Monthly cash flow")
            fig1, ax1 = plt.subplots(figsize=(10, 4))
            ax1.plot(df["date"], df["monthly_cash_flow"])
            ax1.axhline(0, linestyle="--")
            ax1.set_ylabel("Monthly CF ($)")
            ax1.set_xlabel("Date")
            st.pyplot(fig1)

            st.subheader("Cumulative cash flow")
            fig2, ax2 = plt.subplots(figsize=(10, 4))
            ax2.plot(df["date"], df["cumulative_cash_flow"])
            ax2.axhline(0, linestyle="--")
            ax2.set_ylabel("Cumulative CF ($)")
            ax2.set_xlabel("Date")
            st.pyplot(fig2)

            st.subheader("Loan balance")
            fig3, ax3 = plt.subplots(figsize=(10, 4))
            ax3.plot(df["date"], df["balance"])
            ax3.set_ylabel("Balance ($)")
            ax3.set_xlabel("Date")
            st.pyplot(fig3)

            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv_bytes, file_name="simulation.csv", mime="text/csv")

            # Save run to DB and also materialize a CSV per run
            runs_dir = Path(__file__).resolve().parent / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            
            run_id = sim_db.add_run(
                scenario_id=st.session_state.selected_scenario_id,
                kpis=k,
                csv_path=None,  # will set after we know id
                db_path=DB_PATH,
            )
            final_csv = runs_dir / f"run_{run_id}.csv"
            with open(final_csv, "wb") as f:
                f.write(csv_bytes)
            # update path in DB
            # Quick update using sqlite3 directly
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE runs SET csv_path=? WHERE id=?", (str(final_csv), run_id))
            conn.commit()
            conn.close()

            st.success(f"Run saved (id {run_id}).")

        st.markdown("---")
        st.subheader("Down Payment Analysis")
        st.write("Find the minimum down payment percentage needed for positive monthly cash flow.")
        
        with st.form("down_payment_analysis_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                dp_lower = st.number_input("Min down payment (%)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)
            with col2:
                dp_upper = st.number_input("Max down payment (%)", min_value=0.0, max_value=100.0, value=50.0, step=1.0)
            with col3:
                dp_num_sims = st.number_input("Number of simulations", min_value=5, max_value=100, value=25, step=5)
            
            run_dp_analysis = st.form_submit_button("Run Down Payment Analysis")
        
        if run_dp_analysis:
            if dp_lower >= dp_upper:
                st.error("Minimum down payment must be less than maximum.")
            else:
                # Create placeholders for live updates
                progress_bar = st.progress(0)
                status_text = st.empty()
                live_chart = st.empty()
                live_metrics = st.empty()
                
                # Store results as they come in
                live_results = []
                
                def update_progress(current, total, result):
                    """Callback to update UI in real-time"""
                    live_results.append(result)
                    
                    # Update progress bar
                    progress_bar.progress(current / total)
                    
                    # Update status text
                    cf = result['monthly_cash_flow']
                    dp_pct = result['down_payment_percentage']
                    status_text.text(f"Testing {dp_pct:.1f}% down payment... Cash flow: ${cf:,.0f}/month")
                    
                    # Update live chart
                    if len(live_results) > 0:
                        temp_df = pd.DataFrame(live_results)
                        
                        fig_live, ax_live = plt.subplots(figsize=(10, 5))
                        ax_live.plot(temp_df['down_payment_percentage'], temp_df['monthly_cash_flow'], 
                                    marker='o', color='#1f77b4', linewidth=2, markersize=8, label='Monthly Cash Flow')
                        ax_live.plot(temp_df['down_payment_percentage'], temp_df['monthly_mortgage'], 
                                    marker='v', color='#8c564b', linewidth=2, markersize=8, alpha=0.7, label='Monthly Mortgage')
                        ax_live.axhline(y=0, color='red', linestyle='--', linewidth=2, alpha=0.5)
                        
                        # Highlight positive cash flow points
                        positive = temp_df[temp_df['monthly_cash_flow'] > 0]
                        if not positive.empty:
                            ax_live.scatter(positive['down_payment_percentage'], positive['monthly_cash_flow'], 
                                          color='green', s=200, zorder=5, marker='*', label='Positive CF')
                        
                        ax_live.set_xlabel('Down Payment (%)', fontsize=11, fontweight='bold')
                        ax_live.set_ylabel('Monthly Amount ($)', fontsize=11, fontweight='bold')
                        ax_live.set_title('🔴 LIVE: Cash Flow Analysis', fontsize=13, fontweight='bold')
                        ax_live.legend(fontsize=9)
                        ax_live.grid(True, alpha=0.3)
                        plt.tight_layout()
                        
                        live_chart.pyplot(fig_live)
                        plt.close(fig_live)
                        
                        # Show live metrics
                        with live_metrics.container():
                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("Current DP %", f"{dp_pct:.1f}%")
                            col2.metric("Monthly CF", f"${cf:,.0f}", delta=f"${cf:,.0f}" if cf > 0 else None)
                            col3.metric("Simulations", f"{current}/{total}")
                            col4.metric("Status", "✅ Found!" if cf > 0 else "🔍 Searching...")
                
                # Create AutoSim object
                auto_sim = AutoSim(sim)
                
                # Run the analysis with live updates
                results_df, dp_amount, dp_percent = auto_sim.down_payment_for_cashflow(
                    upper_limit=dp_upper,
                    lower_limit=dp_lower,
                    num_simulations=int(dp_num_sims),
                    progress_callback=update_progress
                )
                
                # Clear live updates
                progress_bar.empty()
                status_text.empty()
                live_chart.empty()
                live_metrics.empty()
                
                # Display results
                if dp_amount is not None and dp_percent is not None:
                    st.success(f"✅ Break-even found at **{dp_percent:.2f}%** down payment (${dp_amount:,.0f})")
                    
                    # Show key metrics at break-even
                    be_row = results_df[results_df['down_payment_percentage'] == dp_percent].iloc[0]
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Down Payment", f"${be_row['down_payment']:,.0f}")
                    col2.metric("Monthly Cash Flow", f"${be_row['monthly_cash_flow']:,.0f}")
                    col3.metric("Monthly Mortgage", f"${be_row['monthly_mortgage']:,.0f}")
                    col4.metric("Initial CoC", f"{be_row['initial_coc_percent']:.1f}%")
                else:
                    st.warning(f"⚠️ No positive cash flow found within {dp_lower}% - {dp_upper}% down payment range. Try increasing the upper limit.")
                
                # Show the plot
                st.subheader("Cash Flow vs Down Payment")
                fig_dp, ax_dp = plt.subplots(figsize=(12, 6))
                
                # Plot cash flow and mortgage
                ax_dp.plot(results_df['down_payment_percentage'], results_df['monthly_cash_flow'], 
                          label='Monthly Cash Flow', marker='o', color='#1f77b4', markersize=8, linewidth=2)
                ax_dp.plot(results_df['down_payment_percentage'], results_df['monthly_mortgage'], 
                          label='Monthly Mortgage', marker='v', color='#8c564b', markersize=8, linewidth=2)
                
                # Mark break-even point
                if dp_amount is not None:
                    ax_dp.plot(dp_percent, be_row['monthly_cash_flow'], 'ro', markersize=12, label='Break-Even', zorder=5)
                    ax_dp.annotate(
                        f'Break-Even\n{dp_percent:.2f}%\n${dp_amount:,.0f}',
                        xy=(dp_percent, be_row['monthly_cash_flow']),
                        xytext=(10, 20),
                        textcoords='offset points',
                        fontsize=9,
                        bbox=dict(facecolor='white', edgecolor='green', boxstyle='round,pad=0.5'),
                        arrowprops=dict(arrowstyle='->', color='green', lw=2)
                    )
                
                ax_dp.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.7)
                ax_dp.set_xlabel('Down Payment (%)', fontsize=11)
                ax_dp.set_ylabel('Monthly Amount ($)', fontsize=11)
                ax_dp.set_title('Monthly Cash Flow vs Down Payment Percentage', fontsize=12, fontweight='bold')
                ax_dp.legend(fontsize=10)
                ax_dp.grid(True, alpha=0.3)
                
                st.pyplot(fig_dp)
                
                # Show detailed results table
                with st.expander("View detailed results"):
                    st.dataframe(results_df, use_container_width=True)
                    
                    # Download button for results
                    csv_dp = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download Down Payment Analysis CSV",
                        csv_dp,
                        file_name="down_payment_analysis.csv",
                        mime="text/csv"
                    )

        st.markdown("---")
        st.subheader("Run history")
        hist = sim_db.list_runs(st.session_state.selected_scenario_id, DB_PATH)
        if not hist:
            st.info("No runs saved yet.")
        else:
            dfh = pd.DataFrame(hist)
            st.dataframe(dfh[["id", "run_at", "monthly_mortgage", "initial_coc", "ending_monthly_cf", "cumulative_cf", "terminal_equity", "total_invested_est", "total_return_est", "payback_month", "csv_path"]], use_container_width=True)
