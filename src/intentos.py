"""Frena los intentos de adivinar la contrasena por fuerza bruta.

Vive en memoria a proposito: el panel lo usa una sola persona y reiniciar el
contenedor para saltarse la espera exige acceso al servidor, que es una puerta
mucho mas dificil que la que estamos protegiendo.
"""

import time


class ControlIntentos:
    """Cuenta fallos consecutivos y traduce eso en segundos de espera.

    La espera se duplica con cada fallo a partir del maximo permitido, hasta un
    techo. Un acierto borra el historial.
    """

    def __init__(self, maximo=3, espera_base=5, espera_maxima=300, ahora=None):
        self.maximo = maximo
        self.espera_base = espera_base
        self.espera_maxima = espera_maxima
        self._ahora = ahora or time.monotonic
        self._fallos = 0
        self._ultimo_fallo = 0.0

    def registrar_fallo(self):
        self._fallos += 1
        self._ultimo_fallo = self._ahora()

    def registrar_acierto(self):
        self._fallos = 0
        self._ultimo_fallo = 0.0

    def segundos_de_espera(self):
        """Cuantos segundos faltan para poder reintentar. 0 si se puede ya."""
        if self._fallos < self.maximo:
            return 0

        castigo = min(
            self.espera_base * (2 ** (self._fallos - self.maximo)),
            self.espera_maxima,
        )
        transcurrido = self._ahora() - self._ultimo_fallo
        restante = castigo - transcurrido
        return int(restante) if restante > 0 else 0
