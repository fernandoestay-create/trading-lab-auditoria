# LECCIONES — Laboratorio de trading Exness

### 2026-10-28 — Un juez que no se prueba contra ruido certifica fantasmas

**Contexto:** el torneo certificó tres estrategias sobre paseos aleatorios puros,
una con Sharpe 2,50. La causa: se calculaban retornos *por operación* y se
anualizaban con `sqrt(252)`, como si hubiera una operación diaria. Con 55
operaciones en 12 años hay ~4,6 al año: eso inflaba el Sharpe unas 7 veces.

**Lección:** todo sistema que emite veredictos necesita dos pruebas de calibración,
no una. Contra datos **sin señal** (no debe certificar nada) y contra datos con
**señal inyectada** (debe detectarla). Un sistema que solo pasa la primera puede
estar rechazando todo, que es inútil, no riguroso.

**Cómo aplicarla:** antes de creer cualquier métrica de desempeño, córrela sobre
ruido generado a propósito. Y revisa la anualización: el factor tiene que venir de
la frecuencia **medida** de los eventos, nunca de la frecuencia de las barras.

### 2026-10-29 — Vigilar el veredicto no alcanza: hay que vigilar las CIFRAS

**Contexto:** el centinela diario detectaba si el juez certificaba algo indebido,
pero al reinyectar el bug del `sqrt(252)` **no sonó la alarma**: el juez seguía sin
certificar nada porque el t-stat lo contenía, y sin embargo el Sharpe reportado
volvía a inflarse de 0,41 a 2,50.

**Lección:** un número inflado que nadie certifica sigue siendo un número falso, y
termina copiado en un informe. Las guardias automáticas tienen que comprobar las
cifras, no solo las decisiones. Es L-129 con otra cara.

**Cómo aplicarla:** en cada guardia automática, agrega una banda esperada para las
magnitudes clave, medida y fechada. Y acota el lado que importa: sobre ruido, un
Sharpe muy **negativo** es correcto (los costos castigan), el sospechoso es el
positivo.

### 2026-10-28 — `memory.high` estrangula; para proteger a un vecino, usa un muro

**Contexto:** el primer techo de recursos del laboratorio usaba `MemoryHigh=1G`
para no apretar a Hermes. Con el swap de la máquina ya al 80%, produjo thrashing
indefinido: el load subió de 5,3 a 6,9, el I/O de toda la máquina empeoró, y el
kernel registró **35.150 estrangulamientos**. La protección estaba dañando justo lo
que venía a proteger.

**Lección:** `MemoryHigh` frena al proceso sin matarlo; bajo presión de swap eso se
convierte en daño colateral para toda la máquina. Para aislar de verdad: solo
`MemoryMax` (mata limpio) y `MemorySwapMax=0`.

**Cómo aplicarla:** al poner un techo de recursos, verifica en `memory.events` que
`oom_kill` sube cuando el proceso se excede. Si lo que sube es el contador `high`,
estás estrangulando, no aislando.

### 2026-10-28 — El controlador `io` de cgroups no está delegado en este VPS

**Contexto:** se declaró `IOWeight=20` en el slice del laboratorio para proteger el
I/O de Hermes. `systemctl show` lo reportaba aplicado, pero en el kernel
`io.weight` estaba **ausente**: `cgroup.controllers` del usuario solo tiene
`cpu memory pids`.

**Lección:** `systemctl show` reporta lo que pediste, no lo que el kernel aplica.
Verifica siempre en `/sys/fs/cgroup/.../<controlador>`. Sin delegación del
controlador `io`, la única protección real de I/O es `IOSchedulingClass=idle` por
proceso (`ionice`).

**Cómo aplicarla:** después de crear un slice, lee los archivos del cgroup
directamente. Si falta el archivo del controlador, esa línea del slice no hace nada.

### 2026-10-29 — La IP de salida del VPS depende de si el destino tiene AAAA

**Contexto:** `www.exness-api.com` tiene registro AAAA y el VPS prefiere IPv6, así
que la API lo habría visto llegando desde `2a02:c207:2352:7171::1` y no desde
`<IP-DEL-VPS>`, que es la IPv4 documentada. Con "Allowed IPs" en la IPv4, cada
llamada habría dado 403 sin que el error dijera por qué.

**Lección:** antes de registrar una IP en la lista blanca de cualquier proveedor,
mide **qué IP te ve él**, destino por destino. `my.exness.com` no tiene AAAA y sale
por IPv4; el host de la API sí lo tiene y sale por IPv6. Misma máquina, dos
direcciones distintas.

**Cómo aplicarla:** `curl -4 ifconfig.me` y `curl -6 ifconfig.me`, y `dig AAAA` al
destino real. Si vas a usar lista blanca, fuerza la familia en el cliente
(`httpx.HTTPTransport(local_address="0.0.0.0")`) para que la IP de origen sea
determinista.

### 2026-10-29 — Un hallazgo viral sin medición de acierto no es un hallazgo

**Contexto:** se evaluó MiroFish (82.546 estrellas, 12.485 forks, inversión de un
fondo chino), un motor de "predicción" con miles de agentes LLM. Al buscar en su
README los términos `accuracy`, `validation`, `backtest`, `benchmark`,
`evaluation`, `ground truth`, `Brier`, `calibration`, `baseline`: **cero
coincidencias**.

**Lección:** para cualquier herramienta que *predice*, la primera pregunta no es qué
hace ni cuántas estrellas tiene, sino **qué publica sobre su tasa de acierto**. Si
no publica nada, es un generador de narrativas plausibles. Y más agentes no hacen
la respuesta más correcta: la hacen más convincente, que es peor.

**Cómo aplicarla:** `grep` esos nueve términos en el README antes de leer el resto.
Y verifica las cifras del anuncio contra la API del proveedor: el video decía 33.000
estrellas y eran 82.546 — no era mentira, estaba vieja.

### 2026-10-29 — Un escáner de secretos sensible a mayúsculas se salta archivos

**Contexto:** al comprobar que no hubiera llaves privadas en Drive usé
`find ... ! -name "*pub*"`. El archivo se llamaba `LLAVE_PUBLICA_vps.pem`, y como
`-name` distingue mayúsculas, el filtro no lo excluyó: `find` lo listó justo debajo
del título *"¿hay alguna llave PRIVADA ahí?"* y pareció una exposición de secreto.
Era falsa alarma —`diff` confirmó que era la pública— pero el error de la
comprobación es real: con esa misma lógica, un archivo `MiLlave.PEM` o
`id_rsa.Private` se habría escapado del escaneo.

**Lección:** en cualquier comprobación de secretos, usa coincidencia **insensible a
mayúsculas** (`-iname`, `grep -i`) y **verifica el contenido, no el nombre**. El
nombre del archivo es una convención; el encabezado `-----BEGIN ... PRIVATE KEY-----`
es el hecho. Y separa los comandos: si dos corren seguidos bajo un mismo título, no
se sabe cuál produjo la salida.

**Cómo aplicarla:** antes de un push o de copiar algo a una carpeta sincronizada:
`grep -rliE "BEGIN (RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY" <ruta>`, que mira el
contenido y no depende del nombre.
