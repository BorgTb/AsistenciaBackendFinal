\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{iccmemoria}
[2025/11/10 v2.1 Estilo Memoria de Título - ICC - UTalca (actualizado con doble portada)]

\PassOptionsToClass{12pt,oneside,fleqn,spanish}{report}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{report}}
\ProcessOptions
\LoadClass{report}

\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{babel}
\RequirePackage{graphicx}
\RequirePackage{setspace}
\RequirePackage{lmodern}
\RequirePackage{microtype}
\usepackage{float}

\selectlanguage{spanish}
\bibliographystyle{plain}

\def\utalca{Universidad de Talca}
\def\facdeing{Facultad de Ingeniería}
\def\escdeicc{Escuela de Ingeniería Civil en Computación}
\def\ciudad{Curicó}
\def\pais{Chile}

\def\dedicaname{Dedicatoria}
\def\agradename{Agradecimientos}
\def\resumenname{Resumen}
\def\Abstractname{Abstract}
\def\tblcontname{Tabla de Contenidos}
\def\indfigname{Índice de Figuras}
\def\indtblname{Índice de Tablas}
\def\glosname{Glosario}
\def\appendixpartname{Anexos}

\def\supervisor#1{\def\@supervisor{#1}}
\def\informantes#1#2{\def\@informantex{#1}\def\@informantey{#2}}
\def\adicional#1{\def\@adicional{#1}}
\def\director#1{\def\@director{#1}}
\def\titulo#1{\def\@titulo{#1}}

\setlength\paperheight{297mm}
\setlength\paperwidth{210mm}
\special{papersize=210mm,297mm}

\newdimen\realleftmargin
\newdimen\realrightmargin
\newdimen\realtopmargin
\newdimen\realbottommargin
\newdimen\realheadpos

\realtopmargin    = 3cm
\realleftmargin   = 3cm
\realbottommargin = 2.5cm
\realrightmargin  = 2.5cm
\realheadpos      = 1.5cm

\setlength\oddsidemargin   {\realleftmargin}
\addtolength\oddsidemargin {-1in}

\setlength\textheight{\paperheight}
  \addtolength\textheight {-\realtopmargin}
  \addtolength\textheight {-\realbottommargin}

\setlength\textwidth{\paperwidth}
 \addtolength\textwidth {-\realleftmargin}
 \addtolength\textwidth {-\realrightmargin}

\setlength\topmargin{\realheadpos}
 \addtolength\topmargin {-1in}

\setlength\headsep{\realtopmargin}
 \addtolength\headsep{-\realheadpos}
 \addtolength\headsep{-\headheight}

% ========== Encabezado, logo y pie ==========
\def\makeencabezado{
\begin{center}
\onehalfspacing
{\large\bfseries\MakeUppercase{\utalca}}\\
{\large\MakeUppercase{\facdeing}}\\
{\large\MakeUppercase{\escdeicc}}
\end{center}
\singlespacing
}

\def\logo{
\begin{center}
\includegraphics[width=3cm]{utalca1.png}
\end{center}
}

\def\ingcivil{
\singlespacing
\parbox{180pt}{
Memoria para optar al título de Ingeniero Civil en Computación\\}
}

\def\calificacion{
\doublespacing
\parbox{300pt}{
  El presente documento fue calificado con nota: \line(1,0){50}\\
}
}

\def\footdate{
\bigskip
\ciudad, \pais --- \@date
}

% ========== PORTADAS ==========
\def\maketitle{
\pagestyle{empty}
\setcounter{page}{-1}
\vspace*{-25mm}

% --- Primera portada ---
\logo
\makeencabezado

\bigskip
\begin{center}
  {\Large \bfseries \@titulo\\}
\end{center}

\bigskip
\begin{center}
  {\bfseries \MakeUppercase{\@author}}
\end{center}

\vfill
\doublespacing
{Profesor Guía: \MakeUppercase{\@supervisor}}
\bigskip\bigskip\bigskip
\ingcivil
\footdate
\newpage

% --- Segunda portada (informantes y nota) ---
\vspace*{-25mm}
\logo
\makeencabezado

\bigskip
\begin{center}
  {\Large \bfseries \@titulo\\}
\end{center}

\bigskip
\begin{center}
  {\bfseries \MakeUppercase{\@author}}
\end{center}

\vfill

{Profesor Guía: \MakeUppercase{\@supervisor}}\bigskip


\calificacion
\bigskip

\ingcivil
\footdate

\newpage
\pagestyle{headings}
\onehalfspacing
}

% ========== Resto de entornos idénticos ==========
\newenvironment{dedicatory}{
  \addcontentsline{toc}{chapter}{\dedicaname}
  \thispagestyle{plain}
  \vspace*{15em}
  \begin{flushright}\itshape
}{
  \end{flushright}\newpage
}

\newenvironment{acknowledgment}{
  \addcontentsline{toc}{chapter}{\agradename}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\agradename}}
  \vspace{2em}
}{
  \newpage
}

\newenvironment{resumen}{
  \addcontentsline{toc}{chapter}{\resumenname}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\resumenname}}
  \vspace{2em}
}{
  \newpage
}

\renewenvironment{abstract}{
  \addcontentsline{toc}{chapter}{\Abstractname}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\Abstractname}}
  \selectlanguage{english}
  \vspace{2em}
}{
  \selectlanguage{spanish}\newpage
  \setcounter{page}{1}
  \pagenumbering{arabic}
}

\renewcommand\tableofcontents{
  \addcontentsline{toc}{chapter}{\tblcontname}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\tblcontname}}
  \par\bigskip
  \@starttoc{toc}
  \newpage
}

\renewcommand\listoffigures{
  \addcontentsline{toc}{chapter}{\indfigname}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\indfigname}}
  \par\bigskip
  \@starttoc{lof}
  \newpage
}

\renewcommand\listoftables{
  \addcontentsline{toc}{chapter}{\indtblname}
  \thispagestyle{plain}
  \centerline{\bfseries\MakeUppercase{\indtblname}}
  \par\bigskip
  \@starttoc{lot}
  \newpage
}

\def\@makechapterhead#1{%
  \thispagestyle{plain}
  \vspace*{25mm}
  {\Huge\bfseries \thechapter.\ #1\par}
  \vspace*{7mm}
  \hrule height 2pt
  \bigskip\bigskip\bigskip
}

\newenvironment{glosario}{
  \newpage
  \addcontentsline{toc}{chapter}{\glosname}
  \thispagestyle{plain}
  {\Huge\bfseries \glosname\par}
  \vspace{2em}
  \begin{description}
}{
  \end{description}
}

\renewenvironment{thebibliography}[1]{
  \newpage
  \addcontentsline{toc}{chapter}{\bibname}
  \thispagestyle{plain}
  {\Huge\bfseries \bibname\par}
  \vspace{2em}
  \list{\@biblabel{\@arabic\c@enumiv}}{
    \setlength{\leftmargin}{0pt}
    \usecounter{enumiv}
    \let\p@enumiv\@empty
    \renewcommand\theenumiv{\@arabic\c@enumiv}}
  \sloppy
}{
  \endlist
}

\def\appendixpart{
  \cleardoublepage
  \thispagestyle{empty}
  \setcounter{chapter}{0}
  \addtocontents{toc}{\protect\contentsline{chapter}{\appendixpartname}{}}
  \vspace*{6cm}
  \begin{center}
  {\Huge\bfseries\appendixpartname}
  \end{center}
  \newpage
  \pagestyle{headings}
}

\endinput
