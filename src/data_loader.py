# data_loader.py
import json
import datetime as dt
from pathlib import Path
from typing import Dict, Any
from itertools import chain

import numpy as np
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GliderDataLoader:
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.glider_jsons = dict()
        self.selected_files = []
        self.section_ranges = dict()
        self.load_secsactive2()

    def files_available(self):
        if not self.data_dir.exists():
            return []
        return sorted(
            f.name for f in self.data_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".json"
        )

    def set_selected_files(self, filenames: list[str]):
        self.selected_files = []
        self.glider_jsons = dict()
        for filename in filenames:
            self.load_glider_json(filename)
            self.selected_files.append(filename)

    def latest_filemodified_timestamp(self):
        latest_mtime = 0
        for filename in self.files_available():
            path = self.data_dir / filename
            mtime = path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
        latest_mtime = dt.datetime.fromtimestamp(latest_mtime).isoformat(timespec='seconds')
        return latest_mtime

    def load_glider_json(self, filename=None, force: bool=False) -> Dict[str, Any]:
        if filename in self.glider_jsons and not force:
            return self.glider_jsons[filename]
        if isinstance(filename,str):
            path = self.data_dir / filename
            with path.open() as f:
                content = json.load(f)
            self.glider_jsons[filename] = content
            return content
        elif isinstance(filename,list):
            for f in filename:
                self.load_glider_json(f, force=force)
        else:
            if not self.selected_files:
                self.selected_files = self.files_available()
            for f in self.selected_files:
                self.load_glider_json(f, force=force)

    def load_secsactive2(self):
        """
        Returns dict:
          { "0209": [(1,22), (23,42), ..., (720, np.inf)],
            "0212": [(1,21), (22,42), (43, np.inf)],
            ...
          }
        """
        df = pd.read_csv(self.data_dir/'secsactive2.csv', header=None, names=["sn", "start", "end"], dtype={"sn": int, "start": float, "end": float})
        #df["sn"] = df["sn"].str.zfill(4)

        # parse Inf
        # df["end"] = df["end"].astype(str)
        # df["end"] = df["end"].replace({"Inf": str(np.inf), "inf": str(np.inf)})
        # df["end"] = df["end"].astype(float)

        #df["start"] = df["start"].astype(int)

        self.section_ranges = {}
        for sn, g in df.groupby("sn", sort=False):
            self.section_ranges[sn] = [(int(r.start), float(r.end)) for r in g.itertuples(index=False)]

    def glider_sns(self):
        sns = []
        for filename, glider_json in self.glider_jsons.items():
            sns.append(glider_json['sn'])
        return sns

    def instruments(self):
        insts = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = glider_json['sn']
            for inst_key,val in glider_json.items():
                if isinstance(val, dict) and 'info' in val and 'time' in val:
                    inst_name = val['info']['tag']
                    if inst_name not in insts:
                        insts[inst_name] = dict(gliders=[sn], key=inst_key)
                    else:
                        assert insts[inst_name]['key'] == inst_key
                        insts[inst_name]['gliders'].append(sn)
        return insts

    def dv_fields(self):
        fields = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = glider_json['sn']
            for key,val in glider_json.items():
                if isinstance(val, dict) and 'info' in val:
                    inst_name = val['info']['tag']
                    for field_tag, field_name in val['info']['tags'].items():
                        if field_name == 'time': continue
                        field_meta = val['info']['fields'][field_name]
                        inst_field_tag = f"{inst_name}:{field_name}"
                        if inst_field_tag not in fields:
                            fields[inst_field_tag] = {sn:field_meta}
                        else:
                            fields[inst_field_tag][sn] = field_meta
        return fields

    def sn_to_filename(self, glider_sn):
        for filename, glider_json in self.glider_jsons.items():
            if glider_sn == glider_json['sn']:
                return filename
        raise KeyError(f'glider_sn {glider_sn} not found. Available are: {self.glider_sns()}')

    def filename_to_sn(self, filename):
        return self.glider_jsons[filename]['sn']

    def build_glider_df(self, glider_sn):
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        flat_data = {}
        for key in ['time','lat','lon']:
            flat_data[key] = list(chain.from_iterable(data[key]))
        df = pd.DataFrame(flat_data)

        # your ndive logic
        df["ndive"] = np.repeat(np.arange(1, len(df) // 2 + 1), 2)

        # default if no sec_ranges
        df["section"] = 1

        #print(glider_sn, self.section_ranges.keys())
        if self.section_ranges:
            ranges = self.section_ranges.get(glider_sn)
            if ranges:
                # assign sequential section id based on row order in secactive2.csv
                section = np.full(len(df), np.nan)

                nd = df["ndive"].to_numpy()

                for i, (start, end) in enumerate(ranges, start=1):
                    if np.isinf(end):
                        mask = nd >= start
                    else:
                        mask = (nd >= start) & (nd <= end)
                    section[mask] = i

                # If some dives don’t match any range (shouldn’t happen), set 1 or keep NaN
                df["section"] = np.nan_to_num(section, nan=1).astype(int)

        return df

    def build_uv_df(self, glider_sn):
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]

        midlats = [(divestart + diveend)/2 for divestart,diveend in data['lat']]
        midlons = [(divestart + diveend)/2 for divestart,diveend in data['lon']]
        timestamps = [timestart for timestart,timeend in data['time']]
        flat_data = dict(time=timestamps, lat=midlats, lon=midlons, u=data['u'], v=data['v'])

        df = pd.DataFrame(flat_data)
        df['glider_sn'] = glider_sn

        # ndive for uv: 1..N (since uv is per-dive, not per-endpoint)
        df["ndive"] = np.arange(1, len(df) + 1)

        # default if no sec_ranges
        df["section"] = 1

        if self.section_ranges:
            ranges = self.section_ranges.get(glider_sn)
            if ranges:
                section = np.full(len(df), np.nan)
                nd = df["ndive"].to_numpy()

                for i, (start, end) in enumerate(ranges, start=1):
                    if np.isinf(end):
                        mask = nd >= start
                    else:
                        mask = (nd >= start) & (nd <= end)
                    section[mask] = i

                df["section"] = np.nan_to_num(section, nan=1).astype(int)

        return df

    def glider_ndive_t0(self, glider_sn, ndive):
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        t0 = data['time'][ndive-1][0]
        return t0

    @staticmethod
    def pad_emptys(segment_lengths, inst_data, fill_val = 0):
        padded_block = []
        for data_block, expected_len in zip(inst_data, segment_lengths):
            if len(data_block) == expected_len:
                padded_block.append(data_block)
            elif len(data_block) == 0:
                padded_block.append( [fill_val]*expected_len )
            else:
                raise ValueError('Will cause flattening error')
        return padded_block

    def build_instrument_df(self, glider_sn, instrument_name):
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        instrument_key = self.instruments()[instrument_name]['key']
        data = data[instrument_key].copy()
        flat_data = dict(time=[])

        for dive_num,times in zip(data['ndive'],data['time']):
            #logger.info(f'{glider_sn}, {instrument_name}, {dive_num}/{len(data["time"])}')
            if dive_num is None: continue
            ndive_t0 = self.glider_ndive_t0(glider_sn, dive_num)
            unixtimes = [t+ndive_t0 for t in times]
            flat_data['time'].extend(unixtimes)

        nested_keys = [k for k in data.keys() if k not in ['info','ndive','time']]
        segment_lengths = [len(segment) for segment in data['time']]

        flat_data['ndive'] = list(chain.from_iterable(
            [[dive_num] * seg_len for dive_num, seg_len in zip(data["ndive"], segment_lengths)]
        ))

        for key in nested_keys:
            padded = self.pad_emptys( segment_lengths, data[key])
            flat_data[key] = list(chain.from_iterable( padded ))

        #logger.info(f'{glider_sn}, {instrument_name}: ' + str({key:len(val) for key,val in flat_data.items()}))

        df = pd.DataFrame(flat_data)
        df['glider_sn'] = glider_sn
        df['instrument'] = instrument_name
        return df

    def time_range(self):
        t_min, t_max = dt.datetime.now().timestamp(), 0
        for filename,data in self.glider_jsons.items():
            t_min = min(data['time'][0][0], t_min)
            t_max = max(data['time'][-1][-1], t_max)
        if t_max <= t_min:
            t_max = t_min
            t_min -= 3600
        return t_min, t_max

    def instrument_in_glider(self, instrument_name, glider_sn):
        instrument_key = self.instruments()[instrument_name]['key']
        if instrument_key in self.glider_jsons[self.sn_to_filename(glider_sn)]:
            return True
        return False

