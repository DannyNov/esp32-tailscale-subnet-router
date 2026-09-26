"""PlatformIO factory target. Uses the same blocks/addresses as serial upload."""
from pathlib import Path
import sys
Import('env')
sys.path.insert(0, str(Path(env.subst('$PROJECT_DIR')) / 'tools'))
from build_factory import build_factory


def factory(source, target, env):
    build = Path(env.subst('$BUILD_DIR'))
    app = build / (env.subst('$PROGNAME') + '.bin')
    images = [(env.subst(str(offset)), env.subst(str(path)))
              for offset, path in env.get('FLASH_EXTRA_IMAGES', [])]
    images.append((env.subst('$ESP32_APP_OFFSET'), str(app)))
    esptool = Path(env.PioPlatform().get_package_dir('tool-esptoolpy')) / 'esptool.py'
    build_factory(images, app, env.BoardConfig().get('upload.flash_size'),
                  env.BoardConfig().get('build.mcu'), esptool, env.subst('$PYTHONEXE'),
                  build / 'firmware-factory.bin', build / 'factory-manifest.json')


env.AddCustomTarget('factory', ['$BUILD_DIR/${PROGNAME}.bin'] +
                   [env.subst(str(p)) for _, p in env.get('FLASH_EXTRA_IMAGES', [])],
                   factory, title='Factory image', description='Merge and verify actual upload blocks')
