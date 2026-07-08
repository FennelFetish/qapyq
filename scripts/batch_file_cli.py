import random
from scripts_common import *
from batch.batch_file import BatchFileTask, DestinationPathVariableParser, Mode


MODE_MAP = {
    "copy":    Mode.Copy,
    "move":    Mode.Move,
    "symlink": Mode.Symlink,
}


class BatchFileRunner(CliBatchRunner):
    def _buildTask(self, args: argparse.Namespace) -> BatchFileTask:
        basePath = args.base or self.filelist.commonRoot
        basePath = os.path.abspath(basePath)

        task = BatchFileTask(self.log, self.filelist.files)
        task.destPathTemplate   = args.path_template
        task.mode               = MODE_MAP[args.mode]
        task.basePath           = basePath
        task.flatFolders        = args.flat

        task.includeImages      = not args.no_images
        task.overwriteImages    = args.overwrite_images

        task.includeMasks       = not args.no_masks
        task.maskPathTemplate   = args.mask_template
        task.renameMasks        = args.rename_masks
        task.overwriteMasks     = args.overwrite_masks

        task.includeJson        = not args.no_json
        task.includeTxt         = not args.no_txt
        task.overwriteCaptions  = args.overwrite_captions

        task.createArchive      = bool(args.archive)
        task.archivePath        = args.archive or ""

        if args.overwrite_all:
            task.overwriteImages    = True
            task.overwriteMasks     = True
            task.overwriteCaptions  = True

        return task


    def _printSummary(self, task: BatchFileTask, printLine: ConfirmLinePrinter) -> bool:
        printLine("Mode",               task.mode.name)
        printLine("Base path",          f"'{task.basePath}'")
        printLine("Flat folders",       task.flatFolders)
        print()
        printLine("Path template",      f"'{task.destPathTemplate}'")
        printLine("Example path",       *self._getExamplePaths(task))

        textOverwriteImages = ", OVERWRITE!" if task.includeImages and task.overwriteImages   else ""
        textOverwriteMasks  = ", OVERWRITE!" if task.includeMasks  and task.overwriteMasks    else ""
        textOverwriteJson   = ", OVERWRITE!" if task.includeJson   and task.overwriteCaptions else ""
        textOverwriteTxt    = ", OVERWRITE!" if task.includeTxt    and task.overwriteCaptions else ""

        print()
        printLine("Include images",     task.includeImages, suffix=textOverwriteImages)
        printLine("Include masks",      task.includeMasks,  suffix=textOverwriteMasks)

        if task.includeMasks:
            with printLine.indent():
                printLine("Mask template",  f"'{task.maskPathTemplate}'")
                printLine("Rename masks",   task.renameMasks)

        print()
        printLine("Include json",       task.includeJson, suffix=textOverwriteJson)
        printLine("Include txt",        task.includeTxt, suffix=textOverwriteTxt)
        printLine("Create archive",     f"'{task.archivePath}'" if task.createArchive else False)

        overwrite = any((textOverwriteImages, textOverwriteMasks, textOverwriteJson, textOverwriteTxt))
        return overwrite

    @staticmethod
    def _getExamplePaths(task: BatchFileTask):
        from lib import imagerw

        parser = DestinationPathVariableParser(None)
        parser.basePath    = task.basePath
        parser.flatFolders = task.flatFolders

        for file in random.sample(task.files, min(3, len(task.files))):
            parser.setup(file)
            parser.width, parser.height = imagerw.readSize(file)
            yield parser.parsePath(task.destPathTemplate, overwriteFiles=True)



def readArgs() -> argparse.Namespace:
    argParser = argparse.ArgumentParser(description="Run qapyq's Batch File.")
    argParser.add_argument("--src", action="append", type=str, required=True, help="Source folder(s) to load files from. Can be passed multiple times.")
    argParser.add_argument("--mode", "-m", choices=("copy", "move", "symlink"), required=True, help="How to transfer files to the destination.")
    argParser.add_argument("--base", type=str, default="", help="Base path used to resolve relative parts of the template. Defaults to the common root of all source files.")
    argParser.add_argument("--flat", action="store_true", help="Flatten destination folder structure instead of preserving subfolders.")
    argParser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt and run immediately.")
    argParser.add_argument("--overwrite-all", action="store_true", help="Overwrite all existing files at destination.")

    imgGroup = argParser.add_argument_group("images")
    imgGroup.add_argument("--no-images", action="store_true", help="Do not include image files.")
    imgGroup.add_argument("--overwrite-images", action="store_true", help="Overwrite existing images at destination.")

    maskGroup = argParser.add_argument_group("masks")
    maskGroup.add_argument("--no-masks", action="store_true", help="Do not include mask files.")
    maskGroup.add_argument("--mask-template", type=str, default="{{path}}-masklabel.png", help="Path template used to locate mask files. Defaults to '{{path}}-masklabel.png'.")
    maskGroup.add_argument("--rename-masks", action="store_true", help="Rename masks to match the destination file name. Only applicable if not including images.")
    maskGroup.add_argument("--overwrite-masks", action="store_true", help="Overwrite existing masks at destination.")

    capGroup = argParser.add_argument_group("captions")
    capGroup.add_argument("--no-json", action="store_true", help="Do not include .json caption files.")
    capGroup.add_argument("--no-txt", action="store_true", help="Do not include .txt caption files.")
    capGroup.add_argument("--archive", type=str, default="", help="Archive path, must end with zip extension. If set, write json/txt files into this archive instead of loose files.")
    capGroup.add_argument("--overwrite-captions", action="store_true", help="Overwrite existing json/txt files (or zip archive) at destination.")

    argParser.add_argument("path_template", type=str, help="Destination path template, e.g. '/mnt/data/{{basepath}}/{{name.ext}}'")

    return argParser.parse_args()


if __name__ == "__main__":
    args = readArgs()
    scriptMain("Batch File", args, BatchFileRunner)
