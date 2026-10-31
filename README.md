# Overleaf CV Tailoring Agent

Aplicación web con Streamlit que adapta un currículum en LaTeX a una oferta de
trabajo. Usa Gemini para reescribir viñetas de experiencia existentes, conserva
el resto del archivo y compila el resultado a PDF con `pdflatex`. No está
diseñada para inventar experiencia laboral.

La aplicación puede obtener la descripción desde una URL o usar el texto que
pegues manualmente si el sitio no permite el acceso automático. Antes de
modificar `main.tex`, guarda una copia de respaldo; si falla la compilación,
restaura el archivo original.

## Requisitos

- Python 3.10 o posterior.
- Una clave de API de Gemini, disponible en [Google AI Studio](https://aistudio.google.com/).
- Una distribución de LaTeX que incluya `pdflatex` y lo tenga disponible en el `PATH`.
- Un currículum LaTeX con un archivo `main.tex`.

Ejemplos para instalar LaTeX:

- **Ubuntu/Debian:** `sudo apt install texlive-latex-base`
- **Windows:** instala [MiKTeX](https://miktex.org/download) y asegúrate de que `pdflatex` esté en el `PATH`.
- **macOS:** instala [MacTeX](https://www.tug.org/mactex/) y asegúrate de que `pdflatex` esté en el `PATH`.

## Descargar e instalar

Clona el repositorio:

```bash
git clone https://github.com/ilensf/ModifyCV_Agent.git
cd ModifyCV_Agent
```

También puedes descargar el código como ZIP desde GitHub y abrir una terminal
en la carpeta extraída.

Crea y activa un entorno virtual (recomendado):

```bash
python -m venv .venv
```

En Linux o macOS:

```bash
source .venv/bin/activate
```

En Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instala las dependencias de Python desde `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

## Configuración

1. Copia `.env.example` a `.env`.
2. Abre `.env` y sustituye el valor de ejemplo por tu clave:

   ```dotenv
   GEMINI_API_KEY=tu_clave_de_gemini
   ```

3. No compartas ni publiques el archivo `.env`; contiene una credencial privada.
   El repositorio excluye ese archivo de Git.
4. Coloca tu CV en una carpeta local con un archivo `main.tex`. La aplicación
   usa `./CV_ESPECIFICOS` de forma predeterminada; puedes cambiar la ruta desde
   la interfaz.

## Ejecutar

Desde la carpeta del proyecto y con el entorno virtual activado:

```bash
streamlit run app.py
```

Streamlit mostrará la dirección local para abrir la aplicación en el navegador.
Introduce la URL de la oferta o pega su descripción y pulsa **Tailor and
Generate PDF**. Al terminar, podrás descargar el PDF generado desde la propia
interfaz.

### Atajo opcional `cv` (Linux/macOS)

La instalación no crea ni configura el comando `cv`. Si quieres usarlo como
atajo, primero comprueba si ya existe:

```bash
command -v cv
```

Si devuelve una ruta o definición que ya utilizas, no la sustituyas. Si no
existe, puedes definir el atajo para la terminal actual (cambia la ruta por la
carpeta donde descargaste el proyecto):

```bash
alias cv='cd "/ruta/al/ModifyCV_Agent" && .venv/bin/python -m streamlit run app.py'
```

Después podrás iniciar la aplicación escribiendo `cv`. Para conservar el atajo
entre sesiones, añade esa línea manualmente a `~/.bashrc` o `~/.zshrc`, según
la terminal que uses. No lo añadas si quieres mantener otro comando o alias
llamado `cv`.

## Dependencias

Las dependencias directas de Python están declaradas en [`requirements.txt`](requirements.txt)
y se instalan con `python -m pip install -r requirements.txt`.
