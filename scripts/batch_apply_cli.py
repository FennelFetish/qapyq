import random
from scripts_common import *
from lib.captionfile import FileTypeSelector
from lib.template_parser import TemplateVariableParser
from batch.batch_apply import BatchApplyTask, WriteMode, WRITE_MODE_TYPE, WRITE_MODE_TEXT, CascadeTemplateMode, CASCADE_TEMPLATE_MODE_TEXT


CASCADE_TEMPLATE_MODE_MAP = {
    "add":      CascadeTemplateMode.SetSkipExisting,
    "replace":  CascadeTemplateMode.SetReplace,
    "remove":   CascadeTemplateMode.Remove,
}


class BatchApplyRunner(CliBatchRunner):
    def _buildTask(self, args: argparse.Namespace) -> BatchApplyTask:
        destKey: str    = args.dest
        backupKey: str  = args.backup
        overwrite: bool = args.overwrite

        task = BatchApplyTask(self.log, self.filelist.files, args.template)
        task.stripAround = not args.no_strip_around
        task.stripMulti  = not args.no_strip_repeat
        task.cascade     = not args.no_cascade
        task.deleteJson  = bool(args.delete_json)

        if destKey == "text":
            task.writeMode = WriteMode.SeparateReplace if overwrite else WriteMode.SeparateSkipExisting
        elif destKey == "singletext":
            if not args.singletext_path:
                raise ValueError("Missing destination path for 'singletext' write mode. Set with --singletext-path")
            if args.cascade_template:
                raise ValueError("Cannot set cascade template with singlefile destination.")

            task.writeMode = WriteMode.SingleReplace if overwrite else WriteMode.SingleAppend
            task.destPath = args.singletext_path
        else:
            try:
                keyType, keyName = destKey.split(".")
                task.destKey = keyName.strip()
            except ValueError:
                raise ValueError(f"Invalid destination key: '{destKey}'. Expected: 'tags.tags', 'captions.final', 'text', 'singletext'")

            match keyType:
                case FileTypeSelector.TYPE_CAPTIONS:
                    task.writeMode = WriteMode.CaptionsReplace if overwrite else WriteMode.CaptionsSkipExisting
                case FileTypeSelector.TYPE_TAGS:
                    task.writeMode = WriteMode.TagsReplace if overwrite else WriteMode.TagsSkipExisting
                case _:
                    raise ValueError(f"Invalid destination key type: '{keyType}'. Options: 'tags', 'captions', 'text', 'singletext'")

            if task.deleteJson:
                raise ValueError("Cannot delete json files when writing to json files")

        if backupKey:
            try:
                backupKeyType, backupKeyName = backupKey.split(".")
            except ValueError:
                raise ValueError(f"Invalid backup key '{backupKey}'. Expected json key. Examples: 'tags.backup', 'captions.old'")

            if backupKeyType in (FileTypeSelector.TYPE_CAPTIONS, FileTypeSelector.TYPE_TAGS):
                task.backupType      = backupKeyType
                task.backupKey       = backupKeyName.strip()
                task.overwriteBackup = bool(args.overwrite_backup)
            else:
                raise ValueError(f"Invalid backup key type '{backupKeyType}'. Options: 'tags', 'captions'")

            if task.deleteJson:
                raise ValueError("Cannot delete json files when backup is enabled")

        if args.cascade_template:
            task.cascadeTemplateMode = CASCADE_TEMPLATE_MODE_MAP[args.cascade_template]
            if task.deleteJson:
                raise ValueError("Cannot delete json files when storing cascade templates in json files")

        return task

    def _printSummary(self, task: BatchApplyTask, printLine: ConfirmLinePrinter) -> bool:
        printLine("Template", f"'{task.template}'")

        print("Strip whitespace:")
        with printLine.indent():
            printLine("Leading/trailing",   task.stripAround)
            printLine("Repeating",          task.stripMulti)

        self._printExampleTexts(task)

        printLine("Write mode", task.writeMode.name)

        destKey = WRITE_MODE_TYPE[task.writeMode]
        if destKey in (FileTypeSelector.TYPE_CAPTIONS, FileTypeSelector.TYPE_TAGS):
            destKey += f".{task.destKey}"

        writeModeText = WRITE_MODE_TEXT[task.writeMode].format(key=destKey).replace("overwrite", "OVERWRITE")
        printLine("Destination", writeModeText)
        if task.writeMode in (WriteMode.SingleReplace, WriteMode.SingleAppend):
            printLine("Destination path",   f"'{task.destPath}'")

        if task.backupType:
            print()
            backupKey = f"[{task.backupType}.{task.backupKey}]"
            printLine("Backup to",          backupKey)
            printLine("Overwrite backup",   task.overwriteBackup)

        print()
        printLine("Cascade updates", task.cascade)

        if cascadeTemplateModeText := CASCADE_TEMPLATE_MODE_TEXT.get(task.cascadeTemplateMode):
            cascadeTemplateModeText = cascadeTemplateModeText.format(key=destKey).replace("overwrite", "OVERWRITE")
            printLine("Cascade template",   cascadeTemplateModeText)
            print()

        printLine("Delete json", task.deleteJson)

        overwrite = task.writeMode not in (WriteMode.SeparateSkipExisting, WriteMode.SingleAppend, WriteMode.CaptionsSkipExisting, WriteMode.TagsSkipExisting)
        overwrite |= task.cascadeTemplateMode not in (CascadeTemplateMode.DoNothing, CascadeTemplateMode.SetSkipExisting)
        overwrite |= task.deleteJson
        return overwrite

    @staticmethod
    def _printExampleTexts(task: BatchApplyTask):
        print()
        print("Text preview:")

        parser = TemplateVariableParser()
        for file in random.sample(task.files, min(3, len(task.files))):
            parser.setup(file)
            text = parser.parse(task.template)

            print(f"--- {file} ---")
            print(text or "[Empty Text]")
            print("---")
            print()



def readArgs() -> argparse.Namespace:
    argParser = argparse.ArgumentParser(description="Run qapyq's Batch Apply.")
    argParser.add_argument("--src", action="append", type=str, required=True, help="Source folder(s) to load files from. Can be passed multiple times.")

    argParser.add_argument("--dest", "-d", type=str, required=True, help="Destination key, e.g. 'tags.tags', 'captions.final' or 'text' for separate text files, 'singletext' for a single text file.")
    argParser.add_argument("--singletext-path", type=str, help="Path to output file for 'singletext' destination.")
    argParser.add_argument("--overwrite", action="store_true", help="Overwrite existing keys/files at destination. For 'singletext' destination: Truncate an existing file instead of appending.")
    argParser.add_argument("--delete-json", action="store_true", help="Delete json files afterwards.")
    argParser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt and run immediately.")

    stripGroup = argParser.add_argument_group("whitespace")
    stripGroup.add_argument("--no-strip-around", action="store_true", help="Don't strip leading and trailing whitespace from resulting text.")
    stripGroup.add_argument("--no-strip-repeat", action="store_true", help="Don't strip repeating whitespace from resulting text.")

    cascadeGroup = argParser.add_argument_group("cascade")
    cascadeGroup.add_argument("--no-cascade", action="store_true", help="Don't cascade updates.")
    cascadeGroup.add_argument("--cascade-template", choices=("add", "replace", "remove"), help="Modify the cascade template for the destination key at the file level.")

    bakGroup = argParser.add_argument_group("backup")
    bakGroup.add_argument("--backup", type=str, help="Backup the old value to this key, e.g. 'tags.backup' or 'captions.old'.")
    bakGroup.add_argument("--overwrite-backup", action="store_true", help="Overwrite existing data at backup destination. If disabled, will append increasing counter to backup key.")

    argParser.add_argument("template", type=str, help="Template that defines the text to write.")

    return argParser.parse_args()


if __name__ == "__main__":
    args = readArgs()
    scriptMain("Batch Apply", args, BatchApplyRunner)
