import os


def rename_folders_recursive(base_directory):
    """
    Recursively scans all folders and replaces
    'KXP' with 'KXIP' in folder names.
    """

    # bottom-up traversal is important while renaming folders
    for root, dirs, files in os.walk(base_directory, topdown=False):

        for folder_name in dirs:

            # check if substring exists
            if "PK" in folder_name:

                old_path = os.path.join(root, folder_name)

                # create new folder name
                new_folder_name = folder_name.replace("PK", "PBKS")

                new_path = os.path.join(root, new_folder_name)

                # rename folder
                os.rename(old_path, new_path)

                print(f"Renamed: {old_path}")
                print(f"        -> {new_path}\n")


def main():

    # define your base directory here
    base_directory = r"data\ipl"

    rename_folders_recursive(base_directory)


if __name__ == "__main__":
    main()