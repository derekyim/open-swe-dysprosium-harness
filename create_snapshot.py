import os
from langsmith.sandbox import SandboxClient

client = SandboxClient(api_key=os.environ["LANGSMITH_API_KEY_PROD"])
snapshot = client.create_snapshot(
    name="open-swe",
    docker_image="bracelangchain/deepagents-sandbox:v1",
    fs_capacity_bytes=32 * 1024**3,
)
print(snapshot.id)
