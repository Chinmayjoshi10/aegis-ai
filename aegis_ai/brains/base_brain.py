class BaseBrain:
    """
    Root superclass for all cognitive brains.
    Provides PostgreSQL access + kernel wiring.
    """

    name = "BaseBrain"

    def __init__(self, kernel=None, pg=None):
        self.kernel = kernel
        self.pg = pg
