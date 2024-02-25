"""
Copyright (C) 2024 unoaccaso <https://github.com/Unoaccaso>

Created Date: Sunday, February 25th 2024, 9:49:39 pm
Author: unoaccaso

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the
Free Software Foundation, version 3. This program is distributed in the hope
that it will be useful, but WITHOUT ANY WARRANTY; 
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR 
PURPOSE. See the GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https: //www.gnu.org/licenses/>.
"""

from timeserie.common._typing import (
    type_check,
    _ARRAY_LIKE,
    _FLOAT_LIKE,
    _INT_LIKE,
)

from timeserie.convert import from_array, from_gwpy
from timeserie import CACHE

import cupy
import concurrent
import gwosc
import gwpy.timeseries
import warnings


def _fetch_remote(
    event_name: str,
    detector_id: str,
    duration: _FLOAT_LIKE,
    sampling_rate: _INT_LIKE,
    repeat_on_falure: bool,
    max_attempts: _INT_LIKE,
    current_attempt: _INT_LIKE,
    verbose: bool = False,
    use_gpu: bool = False,
):
    try:
        if verbose:
            print(f"Connecting to gwosc for {event_name}({detector_id})...")
        reference_time_gps = gwosc.datasets.event_gps(event_name)
        if verbose:
            print("done!")
        start_time = reference_time_gps - duration / 2
        end_time = (
            reference_time_gps + duration / 2 + 1 / sampling_rate
        )  # to inlcude last
        timeserie = gwpy.timeseries.TimeSeries.fetch_open_data(
            detector_id,
            start_time,
            end_time,
            sampling_rate,
            verbose=verbose,
        )
        new_duration = timeserie.times.value[-1] - timeserie.times.value[0]
        if new_duration != duration:
            duration = new_duration
            warnings.warn(f"Duration of downloaded data set to: {new_duration}")
        return from_gwpy(
            timeserie,
            event_name,
            detector_id,
            reference_time_gps=reference_time_gps,
            use_gpu=use_gpu,
            duration=duration,
        )
    except ValueError:
        if current_attempt < max_attempts:
            warnings.warn(
                f"Failed downloading {current_attempt}/{max_attempts} times, retrying...",
            )
            _fetch_remote(
                event_name=event_name,
                detector_id=detector_id,
                duration=duration,
                sampling_rate=sampling_rate,
                max_attempts=max_attempts,
                repeat_on_falure=repeat_on_falure,
                current_attempt=current_attempt + 1,
                verbose=verbose,
                use_gpu=use_gpu,
            )
        else:
            raise ConnectionError(
                f"Failed downloading too many times ({current_attempt})"
            )


@type_check(classmethod=True)
def fetch_by_name(
    event_names: str | list[str],
    detector_ids: str | list[str],
    duration: _FLOAT_LIKE = 100.0,
    sampling_rate: _INT_LIKE = 4096,
    repeat_on_falure: bool = True,
    max_attempts: _INT_LIKE = 100,
    verbose: bool = False,
    use_gpu: bool = False,
    force_cache_overwrite: bool = False,
    cache_results: bool = True,
):
    """
    Fetch data for multiple events and detectors and create TimeSeries objects.

    This method fetches data for multiple events and detectors in parallel and creates
    corresponding TimeSeries objects. It provides flexibility in specifying the duration,
    sampling rate, and other parameters for fetching data. Additionally, it handles caching
    of fetched data for improved performance.

    Parameters
    ----------
    event_names : str | list[str]
        Name(s) of the event(s).
    detector_ids : str | list[str]
        Identifier(s) of the detector(s).
    duration : Union[float, float32, float64], optional
        Duration of the time series. Default is 100.0 seconds.
    sampling_rate : Union[int, int32, int64], optional
        Sampling rate of the time series. Default is 4096 Hz.
    repeat_on_failure : bool, optional
        Whether to repeat the fetch operation on failure. Default is True.
    max_attempts : Union[int, int32, int64], optional
        Maximum number of attempts for fetching. Default is 100.
    verbose : bool, optional
        Whether to print verbose output. Default is False.
    use_gpu : bool, optional
        If True, utilize GPU for processing. Default is False.
    force_cache_overwrite : bool, optional
        Whether to force overwrite cached data. Default is False.
    cache_results : bool, optional
        Whether to cache fetched results. Default is True.

    Returns
    -------
    dict
        Dictionary containing TimeSeries objects with keys as event-detector pairs.

    Raises
    ------
    ConnectionError
        If fetching fails after maximum attempts.

    Examples
    --------
    Fetch data for a single event and detector:

    >>> from mylibrary import TimeSeries
    >>> ts_data = TimeSeries.fetch_event(
    ...     event_names="GWEvent1",
    ...     detector_ids="H1",
    ...     duration=50.0,  # Duration set to 50 seconds
    ...     sampling_rate=2048,  # Sampling rate set to 2048 Hz
    ...     verbose=True  # Verbose output enabled
    ... )

    Fetch data for multiple events and detectors:

    >>> ts_data = TimeSeries.fetch_event(
    ...     event_names=["GWEvent1", "GWEvent2"],
    ...     detector_ids=["H1", "L1"],
    ...     duration=100.0,  # Duration set to 100 seconds
    ...     sampling_rate=4096,  # Sampling rate set to 4096 Hz
    ...     use_gpu=True,  # Utilize GPU for processing
    ... )

    """
    if isinstance(event_names, str):
        event_names = [event_names]
    if isinstance(detector_ids, str):
        detector_ids = [detector_ids]
    # if any(
    #     detector_id not in _DECODE_DETECTOR.keys()
    #     for detector_id in detector_ids
    # ):
    #     raise NotImplementedError(f"Unsupported detector id!")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(
                _fetch_remote,
                event_name,
                detector_id,
                duration,
                sampling_rate,
                repeat_on_falure,
                max_attempts,
                1,
                verbose,
                use_gpu,
            )
            for event_name in event_names
            for detector_id in detector_ids
            if (event_name, detector_id) not in CACHE
            or duration != CACHE[(event_name, detector_id)].duration
            or force_cache_overwrite
            or (
                use_gpu
                and not isinstance(
                    CACHE[(event_name, detector_id)],
                    cupy.ndarray,
                )
            )
        ]
        out_var = {}
        for future in futures:
            timeserie = future.result()
            event_name = timeserie.segment_name
            detector_id = timeserie.detector_id
            out_var[(event_name, detector_id)] = timeserie
            event_names.remove(event_name) if event_name in event_names else ...
            detector_ids.remove(detector_id) if detector_id in detector_ids else ...

        # filling all the cached data
        for event_name in event_names:
            for detector_id in detector_ids:
                out_var[(event_name, detector_id)] = CACHE[(event_name, detector_id)]

    if cache_results:
        CACHE.update(out_var)

    return out_var


# TODO
@type_check(classmethod=True)
def fetch_by_gps(): ...