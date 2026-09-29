import os
import re
import shutil
from ojitos369.utils import printwln as pln

class Migrate:
    def replace_media(self, file):
        # vite.config.js ya define base:'/media/dist/' para el build, asi que
        # index.html y los chunks ya traen las rutas absolutas correctas de
        # fabrica. NO reemplazar '/assets/' aqui: esas rutas ya son
        # '/media/dist/assets/...' y un replace ciego las duplicaria
        # ('/media/dist/media/dist/assets/...').
        with open(file, 'r', encoding='utf-8') as f:
            file_str = f.read()
        return file_str

    def main(self, *args, **options):
        # cross-platform (Linux / Windows): paths relative to this file, shutil instead of rm/cp
        root = os.path.dirname(os.path.abspath(__file__))
        media_dir = os.path.join(root, "back", "media", "dist")
        react_build = os.path.join(root, "front", "dist")
        if not os.path.isdir(react_build):
            raise SystemExit("front/dist no existe: compila el front primero (pnpm build)")

        # Borra build anterior y copia el nuevo
        shutil.rmtree(media_dir, ignore_errors=True)
        shutil.copytree(react_build, media_dir)

        # Replace /assets/ -> /media/dist/assets/
        html = self.replace_media(os.path.join(media_dir, "index.html"))

        # get js name
        files = os.listdir(os.path.join(media_dir, 'assets'))
        # pln(files)
        file_name = ''
        js_files = []
        for file in files:
            if file.endswith('.js'):
                js_files.append(file)

        for file_name in js_files:
            pln(file_name)
            js = self.replace_media(os.path.join(media_dir, "assets", file_name))

            structure = r'https?://localhost(:\d+)?'
            matches = re.finditer(structure, js)
            matches = sorted(matches, key=lambda x: len(x.group(0)), reverse=True)
            for match in matches:
                pln(match.group(0))
                js = js.replace(match.group(0), '')
            with open(os.path.join(media_dir, 'assets', file_name), 'w', encoding='utf-8') as f:
                f.write(js)

        # --------------------------------   css   -----------------
        file_name = ''
        css_files = []
        for file in files:
            if file.endswith('.css'):
                css_files.append(file)

        for file_name in css_files:
            pln(file_name)
            css = self.replace_media(os.path.join(media_dir, "assets", file_name))

        pln('Done')


if __name__ == '__main__':
    Migrate().main()
