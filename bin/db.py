import psycopg2
from tenacity import retry, wait_exponential, stop_after_attempt
from typing import Callable


def reconnect(f: Callable):
    def wrapper(storage, *args, **kwargs):
        if not storage.connected():
            storage.connect()

        try:
            return f(storage, *args, **kwargs)
        except psycopg2.Error:
            storage.close()
            raise

    return wrapper


class DB:
    """Postgresql connection that reconnects if connection timed out.

    db = DB(host, user, pw, db)
    cur = db.execute('select x, y from blah')
    """

    def __init__(self, host: str, user: str, pw: str, db: str):
        self.__host = host
        self.__user = user
        self.__pw = pw
        self.__db = db
        self._con = None

    def connected(self) -> bool:
        return self._con and self._con.closed == 0

    def connect(self):
        self.close()
        self._con = psycopg2.connect(
            host=self.__host, user=self.__user, password=self.__pw, database=self.__db
        )

    def close(self):
        if self.connected():
            # noinspection PyBroadException
            try:
                self._con.close()
            except Exception:
                pass

        self._con = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential())
    @reconnect
    def execute(self, s):
        cur = self._con.cursor()
        cur.execute(s)
        return cur
