from distutils.core import setup
import py2exe 

class Target:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.version = "1.1.0.0"
        self.company_name = "Intelitrader"
        self.copyright = "Copyright (c) 2020 Intelitrader."
        self.name = "Primo"

target = Target(
    description = "Primo is a process manager.",
    script = "primo.py",
    dest_base = "Primo")

setup(
	options = {'py2exe': {'bundle_files': 1, 'compressed': True}},
	console=[target]
	)
