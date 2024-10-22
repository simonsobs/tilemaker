# Script for running the entire build process. Similar to docker file,
# but allows for a static-included wheel to be uploaded to pypi.

git clone -b main --single-branch https://github.com/simonsobs/tileviewer.git

cd tileviewer
npm cache clean --force
rm -rf node_modules/.vite
npm install
npm run build

cd ..

rm -rf tilemaker/server/static
mkdir -p tilemaker/server/static
cp -r tileviewer/dist/* tilemaker/server/static

rm -rf tileviewer

python3 -m pip install --upgrade build
python3 -m build
