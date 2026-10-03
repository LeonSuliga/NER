@echo off
setlocal
set ROOT=%~dp0
set PYTHON=%ROOT%.venv\Scripts\python.exe

cd /d "%ROOT%"

echo [1/8] labelstudio_to_project
"%PYTHON%" "%ROOT%scripts\labelstudio_to_project.py"
if errorlevel 1 exit /b %errorlevel%

echo [2/8] convert_dataset
"%PYTHON%" "%ROOT%convert_dataset.py"
if errorlevel 1 exit /b %errorlevel%

echo [3/8] convert_to_spacy
"%PYTHON%" "%ROOT%convert_to_spacy.py"
if errorlevel 1 exit /b %errorlevel%

echo [4/8] train_spacy_ner (spaCy blank)
"%PYTHON%" "%ROOT%train_spacy_ner.py"
if errorlevel 1 exit /b %errorlevel%

echo [5/8] evaluate_model
"%PYTHON%" "%ROOT%scripts\evaluate_model.py"
if errorlevel 1 exit /b %errorlevel%

echo [6/8] train_spacy_vectors (spaCy + pl_core_news_md vectors)
"%PYTHON%" "%ROOT%train_spacy_vectors.py"
if errorlevel 1 exit /b %errorlevel%

echo [7/8] train_herbert_ner (HerBERT transformer)
"%PYTHON%" "%ROOT%train_herbert_ner.py"
if errorlevel 1 exit /b %errorlevel%

echo [8/8] compare_models
"%PYTHON%" "%ROOT%scripts\compare_models.py"
if errorlevel 1 exit /b %errorlevel%

exit /b 0
