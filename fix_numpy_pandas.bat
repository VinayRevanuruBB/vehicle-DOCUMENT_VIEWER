@echo off
echo ========================================
echo NumPy/Pandas Compatibility Fix
echo ========================================
echo This script will fix the numpy/pandas compatibility issue
echo by completely reinstalling both packages in the correct order.
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo Python found: 
python --version
echo.

echo Step 1: Uninstalling existing numpy and pandas...
pip uninstall numpy pandas -y --quiet 2>nul

echo Step 2: Clearing pip cache...
pip cache purge --quiet 2>nul

echo Step 3: Upgrading pip...
python -m pip install --upgrade pip --quiet

echo Step 4: Installing numpy (specific version)...
pip install --no-cache-dir numpy==1.25.2
if errorlevel 1 (
    echo ERROR: Failed to install numpy
    echo Trying alternative approach...
    pip install --no-cache-dir --no-deps numpy==1.25.2
)

echo Step 5: Installing pandas (compatible version)...
pip install --no-cache-dir pandas==2.1.1
if errorlevel 1 (
    echo ERROR: Failed to install pandas
    echo This might be due to missing Microsoft Visual C++ Build Tools
    echo Please install them from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    pause
    exit /b 1
)

echo Step 6: Verifying installation...
python -c "import numpy; import pandas; print('SUCCESS: numpy', numpy.__version__, 'pandas', pandas.__version__)"
if errorlevel 1 (
    echo ERROR: Verification failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS: NumPy and Pandas are now compatible!
echo You can now run your Flask application.
echo ========================================
echo.
pause 