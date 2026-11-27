"""CosmosProof: shows, with proof, what in your Azure Databricks costs money, creates risk or
breaks the LGPD necessity principle without being used."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cosmosproof")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"
