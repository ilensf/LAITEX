# Agente para modificar CVs Overleaf

Aplicación web con Streamlit que adapta un currículum LaTeX a una oferta de
trabajo. Puedes elegir entre **Gemini** y **Groq (Llama 3)** para personalizar
y, si es necesario, traducir el CV completo. El proveedor alternativo se usa
automáticamente si falla el principal.

La app puede obtener la descripción del puesto desde una URL o recibir el texto
pegado manualmente si el sitio bloquea el acceso (por ejemplo, LinkedIn).
También permite indicar
proyectos, nombres o términos que la IA debe mantener sin cambios. No debe
inventar experiencia laboral: reestructura el contenido existente para
adaptarlo a la oferta.

El CV se compila con `pdflatex`. Si la compilación falla, se restaura el
`main.tex` original. Si tiene éxito, también se restaura el original y se guarda
el PDF adaptado en la carpeta del CV con el nombre `CV_ATS_<EMPRESA>.pdf`.

## Requisitos

- Python 3.10 o posterior.
- Una clave de API de al menos uno de los proveedores:
  - [Google AI Studio](https://aistudio.google.com/) para Gemini.
  - [Groq Console](https://console.groq.com/keys) para Groq.
- Se recomienda configurar ambas claves para que la alternativa automática
  pueda funcionar si el proveedor elegido no está disponible.
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
2. Abre `.env` e introduce tus claves API. Configura al menos la del proveedor
   que quieras utilizar; se recomienda añadir ambas para habilitar el cambio
   automático al otro proveedor si falla el principal:

   ```dotenv
   GEMINI_API_KEY=tu_clave_de_google_ai_studio
   GROQ_API_KEY=tu_clave_de_groq
   ```

3. No compartas ni publiques el archivo `.env`: contiene credenciales privadas.
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
Introduce la URL de la oferta o pega su descripción, indica opcionalmente los
términos inmutables y elige **Tailor with Gemini** o **Tailor with Groq**. La
app realizará hasta tres intentos para generar y compilar el CV. Al terminar,
el PDF se guarda en la carpeta del CV con el nombre basado en la empresa
detectada.

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

Las dependencias directas de Python, incluidos los SDK de Gemini y Groq, están
declaradas en [`requirements.txt`](requirements.txt) y se instalan con:

```bash
python -m pip install -r requirements.txt
```
