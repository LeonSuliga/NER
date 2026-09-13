@echo off
setlocal
set ROOT=%~dp0
set PYTHON=%ROOT%.venv\Scripts\python.exe

cd /d "%ROOT%"

echo [1/5] labelstudio_to_project
"%PYTHON%" "%ROOT%scripts\labelstudio_to_project.py"
if errorlevel 1 exit /b %errorlevel%

echo [2/5] convert_dataset
"%PYTHON%" "%ROOT%convert_dataset.py"
if errorlevel 1 exit /b %errorlevel%

echo [3/5] convert_to_spacy
"%PYTHON%" "%ROOT%convert_to_spacy.py"
if errorlevel 1 exit /b %errorlevel%

echo [4/5] train_spacy_ner
"%PYTHON%" "%ROOT%train_spacy_ner.py"
if errorlevel 1 exit /b %errorlevel%

echo [5/5] evaluate_model
"%PYTHON%" "%ROOT%scripts\evaluate_model.py"
if errorlevel 1 exit /b %errorlevel%

exit /b 0
