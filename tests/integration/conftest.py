import sys
import os

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{here}/../bin")

from integration.fixtures.spatials import (
    dn2s1small,
    truncated,
    lotsalakes,
    sigabovenonsig,
)

# so vim black doesn't remove the above line
dn2s1small, truncated, lotsalakes, sigabovenonsig
