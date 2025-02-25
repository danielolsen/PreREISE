import os
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from pandas.tseries.holiday import USFederalHolidayCalendar as calendar  # noqa: N813

from prereise.gather.demanddata.bldg_electrification import const
from prereise.gather.demanddata.bldg_electrification.const import (
    zone_name_shps,
    zone_names,
)
from prereise.gather.demanddata.bldg_electrification.helper import (
    read_shapefile,
    zone_shp_overlay,
)


def bkpt_scale(df, num_points, bkpt, heat_cool):
    """Adjust heating or cooling breakpoint to ensure there are enough data points to fit.

    :param pandas.DataFrame df: load and temperature for a certain hour of the day, wk or wknd.
    :param int num_points: minimum number of points required in df to fit.
    :param float bkpt: starting temperature breakpoint value.
    :param str heat_cool: dictates if breakpoint is shifted warmer for heating or colder for cooling

    :return: (*pandas.DataFrame*) dft -- adjusted dataframe filtered by new breakpoint. Original input df if size of initial df >= num_points
    :return: (*float*) bkpt -- updated breakpoint. Original breakpoint if size of initial df >= num_points
    """

    dft = (
        df[df["temp_c"] <= bkpt].reset_index()
        if heat_cool == "heat"
        else df[df["temp_c"] >= bkpt].reset_index()
    )
    if len(dft) < num_points:
        dft = (
            df.sort_values(by=["temp_c"]).head(num_points).reset_index()
            if heat_cool == "heat"
            else df.sort_values(by=["temp_c"]).tail(num_points).reset_index()
        )
        bkpt = (
            dft["temp_c"][num_points - 1] if heat_cool == "heat" else dft["temp_c"][0]
        )

    return dft.sort_index(), bkpt


def zonal_data(puma_data, hours_utc, year):
    """Aggregate puma metrics to population weighted hourly zonal values

    :param pandas.DataFrame puma_data: puma data within zone, output of zone_shp_overlay()
    :param pandas.DatetimeIndex hours_utc: index of UTC hours.
    :param int year: year of temperature data

    :return: (*pandas.DataFrame*) temp_df -- hourly zonal values of temperature, wetbulb temperature, and darkness fraction
    """
    puma_pop_weights = (puma_data["pop"] * puma_data["frac_in_zone"]) / sum(
        puma_data["pop"] * puma_data["frac_in_zone"]
    )
    zone_states = list(set(puma_data["state"]))
    timezone = max(
        set(list(puma_data["timezone"])), key=list(puma_data["timezone"]).count
    )

    base_year = const.base_year

    stats = pd.Series(
        data=[
            sum(puma_data["pop"] * puma_data["frac_in_zone"]),
            sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(puma_data["ind_area_gbs_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_elec_sh_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data["frac_hp_res"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data["AC_penetration"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_elec_sh_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data["frac_hp_com"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_elec_dhw_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_elec_dhw_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_elec_other_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_elec_cook_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_ff_sh_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_ff_dhw_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"res_area_{base_year}_m2"]
                * puma_data[f"frac_ff_other_res_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"res_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_ff_sh_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_ff_dhw_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(
                puma_data[f"com_area_{base_year}_m2"]
                * puma_data[f"frac_ff_cook_com_{base_year}"]
                * puma_data["frac_in_zone"]
            )
            / sum(puma_data[f"com_area_{base_year}_m2"] * puma_data["frac_in_zone"]),
            sum(puma_data["hdd65_normals"] * puma_data["pop"] / sum(puma_data["pop"])),
            sum(puma_data["cdd65_normals"] * puma_data["pop"] / sum(puma_data["pop"])),
        ],
        index=[
            "pop",
            "res_area_m2",
            "com_area_m2",
            "ind_area_m2_gbs",
            "frac_elec_res_heat",
            "frac_elec_res_hp",
            "frac_elec_res_cool",
            "frac_elec_com_heat",
            "frac_elec_com_hp",
            "frac_elec_dhw_res",
            "frac_elec_dhw_com",
            "frac_elec_other_res",
            "frac_elec_cook_com",
            "frac_ff_res_heat",
            "frac_ff_dhw_res",
            "frac_ff_other_res",
            "frac_ff_com_heat",
            "frac_ff_dhw_com",
            "frac_ff_cook_com",
            "hdd65",
            "cdd65",
        ],
    )

    puma_hourly_temps = pd.concat(
        list(
            pd.Series(data=zone_states).apply(
                lambda x: pd.read_csv(
                    f"https://besciences.blob.core.windows.net/datasets/bldg_el/pumas/{year}/temps/temps_pumas_{x}_{year}.csv"
                ).T
            )
        )
    )
    puma_hourly_temps_wb = pd.concat(
        list(
            pd.Series(data=zone_states).apply(
                lambda x: pd.read_csv(
                    f"https://besciences.blob.core.windows.net/datasets/bldg_el/pumas/{year}/temps_wetbulb/temps_wetbulb_pumas_{x}_{year}.csv"
                ).T
            )
        )
    )
    puma_hourly_dark_frac = pd.concat(
        list(
            pd.Series(data=zone_states).apply(
                lambda x: pd.read_csv(
                    f"https://besciences.blob.core.windows.net/datasets/bldg_el/pumas/{year}/dark_frac/dark_frac_pumas_{x}_{year}.csv"
                ).T
            )
        )
    )

    hours_local = hours_utc.tz_convert(timezone)
    is_holiday = pd.Series(hours_local).dt.date.isin(
        list(
            pd.Series(
                calendar().holidays(start=hours_local.min(), end=hours_local.max())
            ).dt.date
        )
    )

    temp_df = pd.DataFrame(
        {
            "temp_c": puma_hourly_temps[puma_hourly_temps.index.isin(puma_data.index)]
            .mul(puma_pop_weights, axis=0)
            .sum(axis=0),
            "temp_c_wb": puma_hourly_temps_wb[
                puma_hourly_temps_wb.index.isin(puma_data.index)
            ]
            .mul(puma_pop_weights, axis=0)
            .sum(axis=0),
            "date_local": hours_local,
            "hour_local": hours_local.hour,
            "weekday": hours_local.weekday,
            "holiday": is_holiday,
            "hourly_dark_frac": puma_hourly_dark_frac[
                puma_hourly_dark_frac.index.isin(puma_data.index)
            ]
            .mul(puma_pop_weights, axis=0)
            .sum(axis=0),
        }
    )

    return temp_df, stats


def hourly_load_fit(load_temp_df, plot_boolean):
    """Fit hourly heating, cooling, and baseload functions to load data

    :param pandas.DataFrame load_temp_df: hourly load and temperature data
    :param boolean plot_boolean: whether or not create profile plots.

    :return: (*pandas.DataFrame*) hourly_fits_df -- hourly and week/weekend breakpoints and coefficients for electricity use equations
    :return: (*float*) s_wb_db, i_wb_db -- slope and intercept of fit between dry and wet bulb temperatures of zone
    """

    def make_hourly_series(load_temp_df, i):
        daily_points = 10
        result = {}
        for wk_wknd in ["wk", "wknd"]:
            if wk_wknd == "wk":
                load_temp_hr = load_temp_df[
                    (load_temp_df["hour_local"] == i)
                    & (load_temp_df["weekday"] < 5)
                    & ~load_temp_df["holiday"]  # boolean column
                ].reset_index()
                numpoints = daily_points * 5
            elif wk_wknd == "wknd":
                load_temp_hr = load_temp_df[
                    (load_temp_df["hour_local"] == i)
                    & (
                        (load_temp_df["weekday"] >= 5)
                        | load_temp_df["holiday"]  # boolean column
                    )
                ].reset_index()
                numpoints = daily_points * 2

            load_temp_hr_heat, t_bpc = bkpt_scale(
                load_temp_hr, numpoints, t_bpc_start, "heat"
            )

            load_temp_hr_cool, t_bph = bkpt_scale(
                load_temp_hr, numpoints, t_bph_start, "cool"
            )

            lm_heat = sm.OLS(
                load_temp_hr_heat["load_mw"],
                np.array(
                    [
                        [
                            load_temp_hr_heat["temp_c"][j],
                            load_temp_hr_heat["hourly_dark_frac"][j],
                            1,
                        ]
                        for j in range(len(load_temp_hr_heat))
                    ]
                ),
            ).fit()

            s_heat, s_dark, i_heat = (
                lm_heat.params[0],
                lm_heat.params[1],
                lm_heat.params[2],
            )
            s_heat_stderr, s_dark_stderr, n_heat, r_squared_heat = (
                lm_heat.bse[0],
                lm_heat.bse[1],
                lm_heat.nobs,
                lm_heat.rsquared,
            )

            if s_heat > 0:
                lm_heat = sm.OLS(
                    load_temp_hr_heat["load_mw"],
                    np.array(
                        [
                            [load_temp_hr_heat["hourly_dark_frac"][j], 1]
                            for j in range(len(load_temp_hr_heat))
                        ]
                    ),
                ).fit()

                s_heat, s_dark, i_heat = (0, lm_heat.params[0], lm_heat.params[1])

            if (
                s_dark < 0
                or (
                    max(load_temp_hr_heat["hourly_dark_frac"])
                    - min(load_temp_hr_heat["hourly_dark_frac"])
                )
                < 0.3
            ):
                lm_heat = sm.OLS(
                    load_temp_hr_heat["load_mw"],
                    np.array(
                        [
                            [load_temp_hr_heat["temp_c"][j], 1]
                            for j in range(len(load_temp_hr_heat))
                        ]
                    ),
                ).fit()

                s_dark, s_heat, i_heat = (0, lm_heat.params[0], lm_heat.params[1])
                s_heat_stderr, s_dark_stderr, n_heat, r_squared_heat = (
                    lm_heat.bse[0],
                    0,
                    lm_heat.nobs,
                    lm_heat.rsquared,
                )

                if s_heat > 0:
                    lm_heat = sm.OLS(
                        load_temp_hr_heat["load_mw"],
                        np.array([[1] for j in range(len(load_temp_hr_heat))]),
                    ).fit()
                    s_dark, s_heat, i_heat = (0, 0, lm_heat.params[0])

            load_temp_hr_cool["cool_load_mw"] = [
                load_temp_hr_cool["load_mw"][j]
                - (s_heat * t_bph + i_heat)
                - s_dark * load_temp_hr_cool["hourly_dark_frac"][j]
                for j in range(len(load_temp_hr_cool))
            ]

            load_temp_hr_cool["temp_c_wb_diff"] = load_temp_hr_cool["temp_c_wb"] - (
                db_wb_fit[0] * load_temp_hr_cool["temp_c"] ** 2
                + db_wb_fit[1] * load_temp_hr_cool["temp_c"]
                + db_wb_fit[2]
            )

            lm_cool = sm.OLS(
                load_temp_hr_cool["cool_load_mw"],
                np.array(
                    [
                        [
                            load_temp_hr_cool["temp_c"][i],
                            load_temp_hr_cool["temp_c_wb_diff"][i],
                            1,
                        ]
                        for i in range(len(load_temp_hr_cool))
                    ]
                ),
            ).fit()

            s_cool_db, s_cool_wb, i_cool = (
                lm_cool.params[0],
                lm_cool.params[1],
                lm_cool.params[2],
            )

            s_cool_db_stderr = lm_cool.bse[0]
            s_cool_wb_stderr = lm_cool.bse[1]
            n_cool = lm_cool.nobs
            r_squared_cool = lm_cool.rsquared

            t_bph = -i_cool / s_cool_db if -i_cool / s_cool_db > t_bph else t_bph

            #
            if wk_wknd == "wk":
                wk_graph = load_temp_df[
                    (load_temp_df["hour_local"] == i)
                    & (load_temp_df["weekday"] < 5)
                    & ~load_temp_df["holiday"]  # boolean column
                ]
            else:
                wk_graph = load_temp_df[
                    (load_temp_df["hour_local"] == i)
                    & (
                        (load_temp_df["weekday"] >= 5)
                        | load_temp_df["holiday"]  # boolean column
                    )
                ]

            load_temp_hr_cool_func = wk_graph[
                (wk_graph["temp_c"] < t_bph) & (wk_graph["temp_c"] > t_bpc)
            ].reset_index()

            heat_eqn = (
                load_temp_hr_heat["temp_c"] * s_heat
                + load_temp_hr_heat["hourly_dark_frac"] * s_dark
                + i_heat
            )
            load_temp_hr_cool_plot = load_temp_hr_cool[
                load_temp_hr_cool["temp_c"] >= t_bph
            ]
            load_temp_hr_cool_plot = load_temp_hr_cool_plot.reset_index(drop=True)

            cool_eqn = [
                max(
                    load_temp_hr_cool_plot["temp_c"][i] * s_cool_db
                    + (
                        load_temp_hr_cool_plot["temp_c_wb"][i]
                        - (
                            db_wb_fit[0] * load_temp_hr_cool_plot["temp_c"][i] ** 2
                            + db_wb_fit[1] * load_temp_hr_cool_plot["temp_c"][i]
                            + db_wb_fit[2]
                        )
                    )
                    * s_cool_wb
                    + i_cool,
                    0,
                )
                + t_bph * s_heat
                + load_temp_hr_cool_plot["hourly_dark_frac"][i] * s_dark
                + i_heat
                for i in range(len(load_temp_hr_cool_plot))
            ]
            cool_func_eqn = [
                max(
                    ((load_temp_hr_cool_func["temp_c"][i] - t_bpc) / (t_bph - t_bpc))
                    ** 2
                    * (
                        t_bph * s_cool_db
                        + (
                            load_temp_hr_cool_func["temp_c_wb"][i]
                            - (
                                db_wb_fit[0] * load_temp_hr_cool_func["temp_c"][i] ** 2
                                + db_wb_fit[1] * load_temp_hr_cool_func["temp_c"][i]
                                + db_wb_fit[2]
                            )
                        )
                        * s_cool_wb
                        + i_cool
                    ),
                    0,
                )
                + load_temp_hr_cool_func["temp_c"][i] * s_heat
                + load_temp_hr_cool_func["hourly_dark_frac"][i] * s_dark
                + i_heat
                for i in range(len(load_temp_hr_cool_func))
            ]

            # Generate hourly fit plot
            if plot_boolean:
                plt.rcParams.update({"font.size": 20})
                fig, ax = plt.subplots(figsize=(20, 10))

                plt.scatter(wk_graph["temp_c"], wk_graph["load_mw"], color="black")

                plt.scatter(load_temp_hr_heat["temp_c"], heat_eqn, color="red")
                plt.scatter(load_temp_hr_cool_plot["temp_c"], cool_eqn, color="blue")
                plt.scatter(
                    load_temp_hr_cool_func["temp_c"], cool_func_eqn, color="green"
                )

                plt.title(
                    f"zone {zone_name}, hour {i}, {wk_wknd} \n t_bpc = "
                    + str(round(t_bpc, 2))
                    + "  t_bph = "
                    + str(round(t_bph, 2))
                )
                plt.xlabel("Temp (°C)")
                plt.ylabel("Load (MW)")
                os.makedirs(
                    os.path.join(
                        os.path.dirname(__file__), "dayhour_fits", "dayhour_fits_graphs"
                    ),
                    exist_ok=True,
                )
                plt.savefig(
                    os.path.join(
                        os.path.dirname(__file__),
                        "dayhour_fits",
                        "dayhour_fits_graphs",
                        f"{zone_name}_hour_{i}_{wk_wknd}_{base_year}.png",
                    )
                )

            mrae_heat = np.mean(
                [
                    np.abs(heat_eqn[i] - load_temp_hr_heat["load_mw"][i])
                    / load_temp_hr_heat["load_mw"][i]
                    for i in range(len(load_temp_hr_heat))
                ]
            )
            mrae_cool = np.mean(
                [
                    np.abs(cool_eqn[i] - load_temp_hr_cool_plot["load_mw"][i])
                    / load_temp_hr_cool_plot["load_mw"][i]
                    for i in range(len(load_temp_hr_cool_plot))
                ]
            )
            mrae_cool_func = np.mean(
                [
                    np.abs(cool_func_eqn[i] - load_temp_hr_cool_func["load_mw"][i])
                    / load_temp_hr_cool_func["load_mw"][i]
                    for i in range(len(load_temp_hr_cool_func))
                ]
            )

            result[wk_wknd] = {
                f"t.bpc.{wk_wknd}.c": t_bpc,
                f"t.bph.{wk_wknd}.c": t_bph,
                f"i.heat.{wk_wknd}": i_heat,
                f"s.heat.{wk_wknd}": s_heat,
                f"s.dark.{wk_wknd}": s_dark,
                f"i.cool.{wk_wknd}": i_cool,
                f"s.cool.{wk_wknd}.db": s_cool_db,
                f"s.cool.{wk_wknd}.wb": s_cool_wb,
                f"s.heat.stderr.{wk_wknd}": s_heat_stderr,
                f"s.dark.stderr.{wk_wknd}": s_dark_stderr,
                f"n.heat.{wk_wknd}": n_heat,
                f"s.cool.db.stderr.{wk_wknd}": s_cool_db_stderr,
                f"s.cool.wb.stderr.{wk_wknd}": s_cool_wb_stderr,
                f"n.cool.{wk_wknd}": n_cool,
                f"mrae.heat.{wk_wknd}.mw": mrae_heat,
                f"mrae.cool.{wk_wknd}.mw": mrae_cool,
                f"mrae.mid.{wk_wknd}.mw": mrae_cool_func,
                f"r2.heat.{wk_wknd}": r_squared_heat,
                f"r2.cool.{wk_wknd}": r_squared_cool,
            }

        return pd.Series({**result["wk"], **result["wknd"]})

    t_bpc_start = 10
    t_bph_start = 18.3

    db_wb_regr_df = load_temp_df[load_temp_df["temp_c"] >= t_bpc_start]

    db_wb_fit = np.polyfit(db_wb_regr_df["temp_c"], db_wb_regr_df["temp_c_wb"], 2)

    hourly_fits_df = pd.DataFrame(
        [make_hourly_series(load_temp_df, i) for i in range(24)]
    )

    return hourly_fits_df, db_wb_fit


def temp_to_energy(temp_series, hourly_fits_df, db_wb_fit):
    """Compute baseload, heating, and cooling electricity for a certain hour of year

    :param pandas.Series load_temp_series: data for the given hour.
    :param pandas.DataFrame hourly_fits_df: hourly and week/weekend breakpoints and
        coefficients for electricity use equations.
    :param float s_wb_db: slope of fit between dry and wet bulb temperatures of zone.
    :param float i_wb_db: intercept of fit between dry and wet bulb temperatures of zone.

    :return: (*list*) -- [baseload, heating, cooling]
    """
    temp = temp_series["temp_c"]
    temp_wb = temp_series["temp_c_wb"]
    dark_frac = temp_series["hourly_dark_frac"]
    zone_hour = temp_series["hour_local"]

    heat_eng = 0
    mid_cool_eng = 0
    cool_eng = 0

    wk_wknd = (
        "wk"
        if temp_series["weekday"] < 5 and ~temp_series["holiday"]  # boolean value
        else "wknd"
    )

    (
        t_bpc,
        t_bph,
        i_heat,
        s_heat,
        s_dark,
        i_cool,
        s_cool_db,
        s_cool_wb,
    ) = (
        hourly_fits_df.at[zone_hour, f"t.bpc.{wk_wknd}.c"],
        hourly_fits_df.at[zone_hour, f"t.bph.{wk_wknd}.c"],
        hourly_fits_df.at[zone_hour, f"i.heat.{wk_wknd}"],
        hourly_fits_df.at[zone_hour, f"s.heat.{wk_wknd}"],
        hourly_fits_df.at[zone_hour, f"s.dark.{wk_wknd}"],
        hourly_fits_df.at[zone_hour, f"i.cool.{wk_wknd}"],
        hourly_fits_df.at[zone_hour, f"s.cool.{wk_wknd}.db"],
        hourly_fits_df.at[zone_hour, f"s.cool.{wk_wknd}.wb"],
    )

    base_eng = s_heat * t_bph + s_dark * dark_frac + i_heat

    if temp <= t_bph:
        heat_eng = -s_heat * (t_bph - temp)

    if temp >= t_bph:
        cool_eng = (
            s_cool_db * temp
            + s_cool_wb
            * (
                temp_wb
                - (db_wb_fit[0] * temp**2 + db_wb_fit[1] * temp + db_wb_fit[2])
            )
            + i_cool
        )

    if temp > t_bpc and temp < t_bph:
        mid_cool_eng = ((temp - t_bpc) / (t_bph - t_bpc)) ** 2 * (
            s_cool_db * t_bph
            + s_cool_wb
            * (
                temp_wb
                - (db_wb_fit[0] * temp**2 + db_wb_fit[1] * temp + db_wb_fit[2])
            )
            + i_cool
        )

    return [base_eng, heat_eng, max(cool_eng, 0) + max(mid_cool_eng, 0)]


def plot_profile(profile, actual, plot_boolean):
    """Plot profile vs. actual load

    :param pandas.Series profile: total profile hourly load
    :param pandas.Series actual: zonal hourly load data
    :param boolean plot_boolean: whether or not create profile plots.

    :return: (*plot*)
    """

    mrae = [np.abs(profile[i] - actual[i]) / actual[i] for i in range(len(profile))]

    rss = np.sqrt(
        np.mean([(actual[i] - profile[i]) ** 2 for i in range(len(profile))])
    ) / np.mean(actual)

    mrae_avg, mrae_max = np.mean(mrae), max(mrae)

    if plot_boolean:
        fig, ax = plt.subplots(figsize=(20, 10))
        plt.plot(list(profile.index), profile - actual)
        plt.legend(["Profile - Actual"])
        plt.xlabel("Hour")
        plt.ylabel("MW Difference")
        plt.title(
            "Zone "
            + zone_name
            + " Load Comparison \n"
            + "avg mrae = "
            + str(round(mrae_avg * 100, 2))
            + "% \n avg profile load = "
            + str(round(np.mean(profile), 2))
            + " MW"
        )
        os.makedirs(
            os.path.join(os.path.dirname(__file__), "Profiles", "Profiles_graphs"),
            exist_ok=True,
        )
        plt.savefig(
            os.path.join(
                os.path.dirname(__file__),
                "Profiles",
                "Profiles_graphs",
                f"{zone_name}_profile_{year}.png",
            )
        )

    return (
        mrae_avg,
        mrae_max,
        rss,
        np.mean(profile),
        np.mean(actual),
        max(profile),
        max(actual),
    )


def main(zone_name, zone_name_shp, base_year, year, plot_boolean=False):
    """Run profile generator for one zone for one year.

    :param str zone_name: name of load zone used to save profile.
    :param str zone_name_shp: name of load zone within shapefile.
    :param int base_year: data fitting year.
    :param int year: profile year to calculate.
    :param boolean plot_boolean: whether or not create profile plots.
    """

    zone_load = pd.read_csv(
        f"https://besciences.blob.core.windows.net/datasets/bldg_el/zone_loads_{year}/{zone_name}_demand_{year}_UTC.csv"
    )["demand.mw"]

    hours_utc_base_year = pd.date_range(
        start=f"{base_year}-01-01", end=f"{base_year+1}-01-01", freq="H", tz="UTC"
    )[:-1]

    hours_utc = pd.date_range(
        start=f"{year}-01-01", end=f"{year+1}-01-01", freq="H", tz="UTC"
    )[:-1]

    puma_data_zone = zone_shp_overlay(zone_name_shp, zone_shp, pumas_shp)

    temp_df_base_year, stats_base_year = zonal_data(
        puma_data_zone, hours_utc_base_year, year
    )

    temp_df_base_year["load_mw"] = zone_load

    hourly_fits_df, db_wb_fit = hourly_load_fit(temp_df_base_year, plot_boolean)
    os.makedirs(os.path.join(os.path.dirname(__file__), "dayhour_fits"), exist_ok=True)
    hourly_fits_df.to_csv(
        os.path.join(
            os.path.dirname(__file__),
            "dayhour_fits",
            f"{zone_name}_dayhour_fits_{base_year}.csv",
        )
    )

    zone_profile_load_MWh = pd.DataFrame(  # noqa: N806
        {"hour_utc": list(range(len(hours_utc)))}
    )

    temp_df, stats = zonal_data(puma_data_zone, hours_utc, year)

    energy_list = zone_profile_load_MWh.hour_utc.apply(
        lambda x: temp_to_energy(temp_df.loc[x], hourly_fits_df, db_wb_fit)
    )
    (
        zone_profile_load_MWh["base_load_mw"],
        zone_profile_load_MWh["heat_load_mw"],
        zone_profile_load_MWh["cool_load_mw"],
        zone_profile_load_MWh["total_load_mw"],
    ) = (
        energy_list.apply(lambda x: x[0]),
        energy_list.apply(lambda x: x[1]),
        energy_list.apply(lambda x: x[2]),
        energy_list.apply(lambda x: sum(x)),
    )
    zone_profile_load_MWh.set_index("hour_utc", inplace=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "Profiles"), exist_ok=True)
    zone_profile_load_MWh.to_csv(
        os.path.join(
            os.path.dirname(__file__),
            "Profiles",
            f"{zone_name}_profile_load_mw_{year}.csv",
        )
    )

    (
        stats["mrae_avg_%"],
        stats["mrae_max_%"],
        stats["rss_avg_%"],
        stats["avg_profile_load_mw"],
        stats["avg_actual_load_mw"],
        stats["max_profile_load_mw"],
        stats["max_actual_load_mw"],
    ) = plot_profile(zone_profile_load_MWh["total_load_mw"], zone_load, plot_boolean)

    os.makedirs(
        os.path.join(os.path.dirname(__file__), "Profiles", "Profiles_stats"),
        exist_ok=True,
    )
    stats.to_csv(
        os.path.join(
            os.path.dirname(__file__),
            "Profiles",
            "Profiles_stats",
            f"{zone_name}_stats_{year}.csv",
        )
    )


if __name__ == "__main__":
    # Reading Balancing Authority and Pumas shapefiles for overlaying
    zone_shp = read_shapefile(
        "https://besciences.blob.core.windows.net/shapefiles/USA/balancing-authorities/ba_area/ba_area.zip"
    )
    pumas_shp = read_shapefile(
        "https://besciences.blob.core.windows.net/shapefiles/USA/pumas-overlay/pumas_overlay.zip"
    )

    # Use base_year for model fitting
    base_year = const.base_year

    # Weather year to produce load profiles
    year = 2019

    # If produce profile plots
    plot_boolean = False

    for i in range(len(zone_names)):
        zone_name, zone_name_shp = zone_names[i], zone_name_shps[i]
        main(zone_name, zone_name_shp, base_year, year, plot_boolean)

    # Delete the tmp folder that holds the shapefiles localy after the script is run to completion
    shutil.rmtree(os.path.join("tmp"), ignore_errors=False, onerror=None)
