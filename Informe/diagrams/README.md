# Diagramas para la memoria

Carpeta de diagramas del proyecto **Sistema IoT de asistencia con autenticación biométrica e integración empresarial**.

## Contenido

| # | Archivo | Tipo | Herramienta |
|---|---------|------|-------------|
| 1 | `01_flujo_enrolamiento_biometrico.puml` | Secuencia | PlantUML |
| 2 | `02_flujo_marcaje_automatico.puml` | Secuencia | PlantUML |
| 3 | `03_maquina_estados_esp32.puml` | Estados | PlantUML |
| 4 | `04_flujo_login_jwt.puml` | Secuencia | PlantUML |
| 5 | `05_arquitectura_despliegue_docker.puml` | Despliegue | PlantUML |
| 6 | `06_flujo_mqtt_pub_sub.puml` | Componentes | PlantUML |
| 7 | `07_flujo_sincronizacion_bidireccional.puml` | Actividad | PlantUML |
| 8 | `08_pipeline_cifrado_biometrico.tex` | Pipeline | **TikZ nativo** |
| 9 | `09_flujo_integracion_erp.puml` | Secuencia | PlantUML |
| 10 | `10_componentes_esp32.puml` | Componentes | PlantUML |

## Compilar los `.puml` a PDF vectorial

### Opción A — local

Requiere Java + PlantUML (`apt install plantuml` o `brew install plantuml`).

```bash
# PNG (rápido, no vectorial)
plantuml diagrams/*.puml

# PDF vectorial (recomendado para la memoria impresa)
plantuml -tpdf diagrams/*.puml
```

### Opción B — online (sin instalar nada)

1. Abrir https://www.plantuml.com/plantuml/uml/
2. Pegar el contenido del `.puml`
3. Descargar como PDF o SVG

### Opción C — VS Code

Extensión **"PlantUML"** de jebbs → click derecho en el archivo → *Export Current Diagram* → PDF / SVG.

## Insertar en `memoria.tex`

### Para los `.puml` (después de compilarlos a PDF)

```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=0.85\linewidth]{diagrams/01_flujo_enrolamiento_biometrico.pdf}
  \caption{Diagrama de secuencia del enrolamiento biométrico completo.}
  \label{fig:flujo_enrolamiento}
\end{figure}
```

### Para el diagrama 8 (TikZ — se compila junto a la memoria)

En el **preámbulo** de `memoria.tex`, además del `\usepackage{tikz}` que ya tienes:

```latex
\usetikzlibrary{arrows.meta, positioning, shapes.geometric, shadows}
```

En el lugar donde corresponda dentro del capítulo:

```latex
\input{diagrams/08_pipeline_cifrado_biometrico.tex}
```

## Recomendaciones

- **No subas solo los PNG/PDF al repositorio**: versiona también los `.puml` y `.tex` fuente. Los diagramas son código, no imágenes.
- **Vectorial siempre que sea posible**: PDF o SVG. El PNG se pixela al imprimir la memoria.
- **Coherencia visual**: si vas a mezclar PlantUML con tu draw.io existente (`arqui2.drawio.png`), considera regenerar el `arqui2` también en draw.io con el mismo estilo de tipografía y paleta, o migrarlo a PlantUML para uniformar.
- **Numeración**: deja que LaTeX numere las figuras automáticamente. No hardcodees "Figura 4.3" en los `\caption`.
