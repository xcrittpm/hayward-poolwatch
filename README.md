# Hayward Poolwatch para Home Assistant

Integración no oficial para controlar desde Home Assistant los cloradores salinos Hayward
conectados a [poolwatch.hayward.fr](https://poolwatch.hayward.fr).
Usa la misma nube que la web, así que necesitas el módulo WiFi y una cuenta de Poolwatch.

## Qué aparece en Home Assistant

| Tipo | Entidades |
|------|-----------|
| Sensores | Temperatura del agua, pH, redox (ORP), cloro libre, producción del clorador, modo de filtración, señal WiFi |
| Sensores sí/no | Conectado, bomba en marcha, alarma de caudal (FL1), alarma del clorador (AL4), producción baja, alarma bomba de pH, alarma FL2 (solo con módulo de cloro) |
| Interruptores | Filtración, luz de la piscina, relés 1 a 4 (fuentes, etc.) |
| Selector | Modo de filtración (manual, automático, calefacción, smart, intel) |
| Control deslizante | Nivel de producción del clorador (g/h o %) |

Solo se crean las entidades que tu equipo tiene (por ejemplo, el pH solo si hay módulo de pH).
Los relés usan el nombre que les hayas puesto en la web.

## Instalación con HACS

1. Sube esta carpeta a un repositorio de GitHub (público o privado).
2. En Home Assistant: **HACS → ⋮ → Repositorios personalizados**, pega la URL del repositorio
   y elige el tipo **Integración**.
3. Instala **Hayward Poolwatch** y reinicia Home Assistant.
4. **Ajustes → Dispositivos y servicios → Añadir integración → Hayward Poolwatch**
   y escribe tu email y contraseña de Poolwatch.

### Instalación manual

Copia `custom_components/hayward_poolwatch` dentro de la carpeta `config/custom_components/`
de Home Assistant y reinicia.

## Avisos

- Lee los datos cada 30 segundos. Tras enviar una orden, vuelve a leer a los 15 segundos (el equipo tarda unos 10 en confirmarla).
- El interruptor de filtración enciende o apaga la bomba. En modo automático el equipo puede
  volver a cambiarla según su horario; ponlo en **Manual** si quieres control total.
- Es una integración no oficial: si Hayward cambia su web, puede dejar de funcionar.

## Depuración

Añade esto a `configuration.yaml` para ver en el registro lo que se envía y recibe:

```yaml
logger:
  logs:
    custom_components.hayward_poolwatch: debug
```
