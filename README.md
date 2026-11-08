# Hayward Poolwatch para Home Assistant

Integración no oficial para controlar desde Home Assistant los cloradores salinos Hayward
conectados a [poolwatch.hayward.fr](https://poolwatch.hayward.fr).
Usa la misma nube que la web, así que necesitas el módulo WiFi y una cuenta de Poolwatch.

## Qué aparece en Home Assistant

| Tipo | Entidades |
|------|-----------|
| Sensores | Temperatura del agua, pH, redox (ORP), cloro libre, producción del clorador, modo de filtración del equipo, **horas de filtración hoy**, **horas de la célula del clorador** (total y parcial), desfase del reloj, señal WiFi |
| Sensores sí/no | Conectado, bomba en marcha, alarma de caudal (FL1), alarma del clorador (AL4), producción baja, alarma bomba de pH, alarma FL2 (solo con módulo de cloro) |
| Interruptores | Luz de la piscina, filtración, relés 1 a 4 (fuentes, cascadas, etc.) |
| Selectores | Modo de la luz, modo de filtración y modo de cada relé |
| Números | Tiempo máximo de la luz, de la filtración y de cada relé · nivel de producción del clorador · **pH máximo y mínimo (consigna)** |
| Horas | Inicio y fin del horario de la luz, de los 3 intervalos de filtración y de las 2 franjas de cada relé |
| Botón | Sincronizar hora del equipo |
| Hora automática | Interruptor «Sincronización automática de hora» y su frecuencia en horas (6 por defecto) |

Solo se crean las entidades que tu equipo tiene (por ejemplo, el pH solo si hay módulo de pH).
Los relés usan el nombre que les hayas puesto en la web.

### Elegir qué relés usas

**Ajustes → Dispositivos y servicios → Hayward Poolwatch → Configurar** y marca solo los relés
que tengas conectados. Los demás desaparecen de Home Assistant.

## Cómo funcionan la luz, la filtración y los relés

Cada uno tiene un **modo** y un **tiempo máximo**:

- **Manual:** el interruptor enciende y apaga directamente, sin límite de tiempo.
- **Periodo** (luz y relés) o **Auto / Smart / Intel** (filtración): sigue el horario que tengas
  en Poolwatch, y además el interruptor sigue funcionando:
  - **Encender fuera de horario:** añade al horario del propio equipo una franja
    "desde ahora hasta ahora + tiempo máximo". **El equipo la apaga solo al final, aunque no haya
    internet ni Home Assistant.** Después vuelve tu horario normal.
  - **Apagar dentro del horario:** pasa a manual y apagado hasta que acaba la franja actual, y
    luego vuelve a activar el horario. Mañana funciona como siempre.
  - En **Smart, Intel o calefacción** el equipo calcula él mismo cuándo filtra, así que al
    apagar se queda apagada el tiempo máximo y luego vuelve al modo que tenías.

Si al volver al horario no hay internet o Poolwatch está caído, se reintenta a los
5, 15, 30, 60 y 90 minutos. Si fallan todos, aparece un aviso en Home Assistant; mientras tanto
queda en manual y **apagado** (nunca se queda encendido). Se arregla eligiendo otra vez su modo,
o solo al reiniciar Home Assistant. Lo pendiente se guarda y sobrevive a los reinicios.

## Cambiar el horario desde Home Assistant

En la página del dispositivo, sección **Configuración**, están las horas de inicio y fin de cada
horario. Es lo mismo que ves en la app y la web de Poolwatch: si lo cambias en un sitio, aparece
en el otro (Home Assistant lo lee cada 30 segundos).

- Un fin a las **00:00** significa hasta medianoche. Una franja de 00:00 a 00:00 es una franja sin usar.
- Si el equipo está en **Manual**, ignora los cambios de horario: la integración los guarda y los
  envía al elegir un modo con horario (la entidad lo indica con el atributo `pending`).
- Si cambias el horario durante un encendido o apagado temporal, se aplica al terminar.

### La hora del equipo

Las horas son las del **reloj del controlador**, que puede ir adelantado o atrasado. El sensor
**Desfase del reloj del equipo** dice cuántos minutos va desviado, y el botón
**Sincronizar hora del equipo** lo pone en hora (el mismo comando que usa la web de Poolwatch).
Ojo: al sincronizarlo, tus horarios pasan a cumplirse a la hora real, así que si los habías
ajustado al reloj desviado, revísalos.

Para no tener que acordarte, activa **Sincronización automática de hora**: lo pone en hora al
activarlo y después cada **Frecuencia sincronización automática de hora** (6 horas por defecto).
Si falla (sin internet), lo reintenta a los 15 minutos.

### Si cambias algo a la vez en Home Assistant y en la app

Manda el último cambio que llega al equipo. Antes de cada cambio, Home Assistant vuelve a leer
el estado actual, así que no deshace lo que acabes de cambiar en la app. Solo puede chocar si
cambias lo mismo en los dos sitios en los mismos ~10 segundos (lo que tarda el equipo en
confirmar un cambio).

## Avisos al móvil (opcional)

La integración trae una plantilla de automatización para recibir un aviso en el móvil cuando:

- la piscina se desconecta de Poolwatch durante X minutos,
- salta una alarma (caudal, clorador, bomba de pH…),
- el pH se sale del rango que elijas durante X minutos.

No se activa sola: si la quieres, impórtala con este botón y crea una automatización a partir de ella.

[![Importar plantilla](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fxcrittpm%2Fhayward-poolwatch%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhayward_poolwatch%2Favisos_piscina.yaml)

Necesita la app de Home Assistant en el móvil.

## Notas sobre algunos datos

- **Horas de filtración hoy:** Poolwatch no da este dato, así que lo cuenta la integración mientras
  Home Assistant está encendido. Se pone a cero a medianoche.
- **Horas de la célula:** la web de Poolwatch no las muestra; se interpretan como segundos
  convertidos a horas. Tómalas como orientativas.
- **pH máximo / mínimo:** son las consignas de la bomba de pH, las mismas que en la web
  (Configuración → Consignas).

## Instalación

### Desde el Marketplace (Home Assistant 2026.11 o posterior)

1. **Ajustes → Marketplace → Añadir desde enlace** y pega la URL de este repositorio.
2. Instala **Hayward Poolwatch** y reinicia Home Assistant.
3. **Ajustes → Dispositivos y servicios → Añadir integración → Hayward Poolwatch**
   y escribe tu email y contraseña de Poolwatch.

### Con HACS (versiones anteriores)

**HACS → ⋮ → Repositorios personalizados**, pega la URL de este repositorio con el tipo
**Integración**, instala y sigue desde el paso 2.

### Manual

Copia `custom_components/hayward_poolwatch` dentro de la carpeta `config/custom_components/`
de Home Assistant y reinicia.

## Avisos

- Lee los datos cada 30 segundos. Tras enviar una orden, vuelve a leer a los 15 segundos (el equipo tarda unos 10 en confirmarla).
- Las franjas usan la hora del propio equipo (que puede ir adelantada o atrasada), no la de Home Assistant.
- Las franjas que pasarían de medianoche se cortan a las 24:00 (aún sin probar si el equipo las acepta).
- El equipo ignora los cambios de horario mientras está en Manual; la integración los guarda y los aplica al volver a un modo con horario.
- Es una integración no oficial: si Hayward cambia su web, puede dejar de funcionar.

## Depuración

Si algo falla, descarga el diagnóstico en **Ajustes → Dispositivos y servicios → Hayward Poolwatch → ⋮ → Descargar diagnósticos**. Lleva tus datos personales tapados (email, contraseña, identificadores, dirección, nombres de relés).

Para ver en el registro lo que se envía y recibe, añade esto a `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hayward_poolwatch: debug
```
