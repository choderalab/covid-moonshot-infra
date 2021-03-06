import datetime as dt
import os
from typing import Optional
import json
import logging

import fire
from typing import Callable

import fah_xchem
from .analysis import analyze_compound_series
from .schema import (
    AnalysisConfig,
    FahConfig,
    CompoundSeries,
    CompoundSeriesAnalysis,
    Model,
)


class TimestampedAnalysis(Model):
    as_of: dt.datetime
    series: CompoundSeriesAnalysis


def _get_config(
    cls,
    config_file: Optional[str],
    description: str,
    decoder: Callable[[str], object] = json.loads,
):
    if config_file is None:
        return cls()
    else:
        logging.info("Reading %s from '%s'", description, config_file)
        with open(config_file, "r") as infile:
            config = cls.parse_obj(decoder(infile.read()))

    logging.info("Using %s: %s", description, config)
    return config


def run_analysis(
    compound_series_file: str,
    config_file: Optional[str] = None,
    fah_projects_dir: str = "projects",
    fah_data_dir: str = "data",
    output_dir: str = "results",
    cache_dir: Optional[str] = None,
    num_procs: Optional[int] = 8,
    log: str = "WARN",
):
    """
    Run free energy analysis and write JSON-serialized analysis
    consisting of input augmented with analysis results


    Parameters
    ----------
    compound_series_file : str
        File containing compound series as JSON-encoded :class:`~fah_xchem.schema.CompoundSeries`
    config_file : str, optional
        File containing analysis configuration as JSON-encoded :class:`~fah_xchem.schema.AnalysisConfig`
    fah_projects_dir : str, optional
        Path to Folding@home projects directory
    fah_data_dir : str, optional
        Path to Folding@home data directory
    cache_dir : str, optional
        If given, cache intermediate analysis results in local
        directory of this name
    num_procs : int, optional
        Number of parallel processes to run
    """

    logging.basicConfig(level=getattr(logging, log.upper()))

    compound_series = _get_config(
        CompoundSeries, compound_series_file, "compound series"
    )

    config = _get_config(AnalysisConfig, config_file, "analysis configuration")

    series_analysis = analyze_compound_series(
        series=compound_series,
        config=config,
        server=FahConfig(projects_dir=fah_projects_dir, data_dir=fah_data_dir),
        num_procs=num_procs,
    )

    timestamp = dt.datetime.now(dt.timezone.utc)
    output = TimestampedAnalysis(as_of=timestamp, series=series_analysis)

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "analysis.json"), "w") as output_file:
        output_file.write(output.json())


def generate_artifacts(
    compound_series_analysis_file: str,
    fah_projects_dir: str,
    fah_data_dir: str,
    output_dir: str = "results",
    base_url: str = "/",
    config_file: Optional[str] = None,
    cache_dir: Optional[str] = None,
    num_procs: Optional[int] = None,
    snapshots: bool = True,
    plots: bool = True,
    report: bool = True,
    website: bool = True,
    log: str = "WARN",
) -> None:
    """
    Given results of free energy analysis as JSON, generate analysis
    artifacts in `output_dir`

    By default the following are generated:

    - representative snapshots
    - plots
    - PDF report
    - static HTML for website

    Parameters
    ----------
    compound_series_analysis_file : str
        File containing analysis results as JSON-encoded :class:`~fah_xchem.schema.CompoundSeriesAnalysis`
    fah_projects_dir : str
        Path to directory containing Folding@home project definitions
    fah_data_dir : str
        Path to directory containing Folding@home project result data
    output_dir : str, optional
        Write output here
    base_url : str, optional
        Base URL to use for links in the static site. E.g. if using S3, something like
        https://fah-ws3.s3.amazonaws.com/covid-moonshot/sprints/sprint-4/2020-09-06-ugi-tBu-x3110-3v3m-2020-04-Jacobs/
    config_file : str, optional
        File containing analysis configuration as JSON-encoded :class:`~fah_xchem.schema.AnalysisConfig`
    cache_dir : str or None, optional
        If given, cache intermediate results in a local directory with this name
    num_procs : int or None, optional
        Maximum number of concurrent processes to run for analysis
    snapshots : bool, optional
        Whether to generate representative snapshots
    plots : bool, optional
        Whether to generate plots
    report : bool, optional
        Whether to generate PDF report
    website : bool, optional
        Whether to generate HTML for static site
    log : str, optional
        Logging level
    """

    logging.basicConfig(level=getattr(logging, log.upper()))

    config = _get_config(AnalysisConfig, config_file, "analysis configuration")

    with open(compound_series_analysis_file, "r") as infile:
        tsa = TimestampedAnalysis.parse_obj(json.load(infile))

    return fah_xchem.analysis.generate_artifacts(
        series=tsa.series,
        timestamp=tsa.as_of,
        projects_dir=fah_projects_dir,
        data_dir=fah_data_dir,
        output_dir=output_dir,
        base_url=base_url,
        config=config,
        cache_dir=cache_dir,
        num_procs=num_procs,
        snapshots=snapshots,
        plots=plots,
        report=report,
        website=website,
    )


def main():
    fire.Fire({"run_analysis": run_analysis, "generate_artifacts": generate_artifacts})
