# Local infrastructure

The repository-root `compose.yaml` starts FalkorDB and a separate Redis broker. FalkorDB owns graph state; Redis will carry transient worker jobs in a later milestone.
