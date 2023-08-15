# Thinkific Downloader


## Note

- La descarga de cursos va en contra de los Términos de servicio de Thinkific, ¡NO soy responsable de ninguna acción tomada contra su cuenta como resultado del uso de este programa!

- Este script se encuentra en desarrollo, el código se proporciona tal cual y no soy responsable de ningún problema legal que surja del uso de este programa.


## Description

Script de utilidad para descargar cursos desde cualquier plataforma que utilice Thinkific como proveedor de servicios.

Windows es el sistema operativo de desarrollo principal, pero me he esforzado por admitir también Linux (Mac no probado)


## Requirements

Para el correcto funcionamiento del script utiliza un paquete externo [aria2](https://github.com/aria2/aria2) para descargar los archivos

_**Note**:_ _¡Este paquete debe instalarse globalmente y agregarse a sus variables de entorno, no haciendo uso del comando pip!_


## Install

```bash
pip install -r requirements.txt
```


## Cookies

Para poder descargar un curso es obligatorio el uso de cookies.

El argumento --browser nos permite especificar de qué navegador queremos extraer las cookies, los navegadores compatibles son:

-   brave
-   chrome
-   chromium
-   edge
-   firefox
-   opera
-   safari
-   vivaldi

_**Note**:_ _¡Se recomienda hacer uso del navegador Firefox!_


## Download Directory

El curso se descargara de forma predeterminada en `out`, pero puede especificar su propia ruta de descarga utilizando el argumento `--directory`.

