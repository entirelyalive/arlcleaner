# Paths for image processing test directories
# Base root directory containing the test folders
DATA_ROOT = '/mnt/rawdata/pyarl'

# Specific folders used for SID and TIFF tests
SID_INPUT = DATA_ROOT + '/TestSIDInput'
SID_OUTPUT = DATA_ROOT + '/TestSIDOutput'
TIFF_INPUT = DATA_ROOT + '/TestTIFFInput'
TIFF_OUTPUT = DATA_ROOT + '/TestTIFFOutput'

# Where to store logs for failed conversions
ERROR_LOGS = DATA_ROOT + '/ErrorLogs'

# Directory where files that fail processing are moved
FAILED_PROCESSING = DATA_ROOT + '/FailedProcessing'

# Quality for JPEG compression when converting imagery
JPEG_QUALITY = 90

# Pixel dimensions for SID tiling
SID_TILE_WIDTH = 5000
SID_TILE_HEIGHT = 5000
