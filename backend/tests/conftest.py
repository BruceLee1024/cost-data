import os
import tempfile

os.environ["COST_DATA_HOME"] = tempfile.mkdtemp(prefix="cost-data-tests-")
os.environ["COST_DATA_SESSION_TOKEN"] = "test-session-token"
