# Hayward Poolwatch para Home Assistant

Integración no oficial para controlar desde Home Assistant los cloradores salinos Hayward
conectados a [poolwatch.hayward.fr](https://poolwatch.hayward.fr).
Usa la misma nube que la web, así que necesitas el módulo WiFi y una cuenta de Poolwatch.

## Qué aparece en Home Assistant

| Tipo | Entidades |
|------|-----------|
| Sensores | Temperatura del agua, pH, redox (ORP), cloro libre, producción del clorador, modo de filtración del equipo, señal WiFi |
| Sensores sí/no | Conectado, bomba en marcha, alarma de caudal (FL1), alarma del clorador (AL4), producción baja, alarma bomba de pH, alarma FL2 (solo con módulo de cloro) |
| Interruptores | Luz de la piscina, filtración, relés 1 a 4 (fuentes, cascadas, etc.) |
| Selectores | Modo de la luz, modo de filtración y modo de cada relé |
| Números | Tiempo máximo de la luz, de la filtración y de cada relé · nivel de producción del clorador |

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

Añade esto a `configuration.yaml` para ver en el registro lo que se envía y recibe:

```yaml
logger:
  logs:
    custom_components.hayward_poolwatch: debug
```
