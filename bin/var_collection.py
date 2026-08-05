import logging
import pathlib
import json
import numpy as np
from jinja2 import Environment, FileSystemLoader
from netCDF4 import Dataset


class VarCollection:
    """Collection of related variables"""

    def __init__(self, attrs, outfile, con, top):
        """Setup, define and write a bunch of related variables"""
        self.name = type(self).__name__.lower()
        self.attrs = attrs
        self.outfile = outfile
        self.con = con
        self.top = top
        self.preamble()
        self.setup_vars()
        self.dfn_vars()
        self.write_vars()
        self.postlude()

    def preamble(self):
        pass

    def setup_vars(self):
        # get the types and attributes for the flow stats variables
        logging.info(f"Getting {self.name} variable types/attributes")
        mydir = pathlib.Path(__file__).resolve().parent
        template = Environment(loader=FileSystemLoader(searchpath=mydir)).get_template(
            "attr_info.jinja"
        )
        self.v2info = json.loads(template.render(self.attrs))[f"{self.name}_vars"]

        # maps variable name to numpy array for data
        self.v2val = {
            v: np.full([self.attrs[d] for d in info["dims"]], info["fillvalue"], dtype=float)
            for v, info in self.v2info.items()
        }

    def setup_dim(self, dimname, dimlen):
        logging.info(f"Setting dim {dimname}")
        nc = Dataset(self.outfile, "a", format="NETCDF4")
        nc.createDimension(dimname, dimlen)
        nc.close()

    def dfn_vars(self):
        pass

    def write_vars(self):
        # put in the data into netcdf
        logging.info(f"Populating output with {self.name} variables")
        nc = Dataset(self.outfile, "a", format="NETCDF4")
        for v, info in self.v2info.items():
            logging.debug(f"creating variable {v}")
            var = nc.createVariable(
                v, info["type"], info["dims"], fill_value=info.get("fillvalue", None)
            )
            var[:] = self.v2val[v] / info["attributes"].get("scale_factor", 1)
            for key, val in info["attributes"].items():
                setattr(var, key, val)
        nc.close()

    def postlude(self):
        del self.v2val
