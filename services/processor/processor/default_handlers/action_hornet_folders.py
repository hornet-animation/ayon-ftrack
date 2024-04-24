#!/usr/bin/env python3

import re
import os
import sys
from ftrack_common.event_handlers import ServerAction
from ayon_api import get_addons_project_settings, get_project_anatomy_preset, get as ayon_get
import json

def get_project_basic_paths(project_name):
    project_settings = get_project_settings(project_name)
    folder_structure = (
        project_settings["global"]["project_folder_structure"]
    )
    if not folder_structure:
        return []

    if isinstance(folder_structure, six.string_types):
        folder_structure = json.loads(folder_structure)
    return _list_path_items(folder_structure)


class CreateHornetFolders(ServerAction):
    """Action create folder structure and may create hierarchy in Ftrack.

    Creation of folder structure and hierarchy in Ftrack is based on presets.
    These presets are located in:
    `~/pype-config/presets/tools/project_folder_structure.json`

    Example of content:
    ```json
    {
        "__project_root__": {
            "prod" : {},
            "resources" : {
              "footage": {
                "plates": {},
                "offline": {}
              },
              "audio": {},
              "art_dept": {}
            },
            "editorial" : {},
            "assets[ftrack.Library]": {
              "characters[ftrack]": {},
              "locations[ftrack]": {}
            },
            "shots[ftrack.Sequence]": {
              "scripts": {},
              "editorial[ftrack.Folder]": {}
            }
        }
    }
    ```
    Key "__project_root__" indicates root folder (or entity). Each key in
    dictionary represents folder name. Value may contain another dictionary
    with subfolders.

    Identifier `[ftrack]` in name says that this should be also created in
    Ftrack hierarchy. It is possible to specify entity type of item with "." .
    If key is `assets[ftrack.Library]` then in ftrack will be created entity
    with name "assets" and entity type "Library". It is expected Library entity
    type exist in Ftrack.
    """

    identifier = "ayon.create.hornet.structure"
    label = "Hornet - Folders"
    description = "Creates folder structure"
    role_list = ["Administrator", "Project Manager"]

    settings_key = "prepare_project"
    pattern_array = re.compile(r"\[.*\]")
    pattern_ftrack = re.compile(r".*\[[.]*ftrack[.]*")
    pattern_ent_ftrack = re.compile(r"\[ftrack\.[^.,\],\s,]*\]")
    pattern_template = re.compile(r"\{.*\}")
    project_root_key = "__project_root__"
    drives = {
        'windows': {
            'production': 'P:\\',
            'producers':  'O:\\',
            'edit':  'I:\\',
        },
        'linux': {
            'production': '/mnt/prod/',
            'producers': '/mnt/producers/',
            'edit': '/mnt/edit/'
        }
    }
    platform = 'linux' if 'linux' in sys.platform.lower() else 'windows'
    #not sure why roots is a single item list of a dict

    def discover(self, session, entities, event):
        """Show only on project."""
        if (
            len(entities) != 1
            or entities[0].entity_type.lower() != "project"
        ):
            return False

        return self.valid_roles(session, entities, event)

    def launch(self, session, entities, event):
        # Get project entity
        self.project_name = entities[0]['full_name']
        self.project_root = json.loads(ayon_get(f'/projects/{self.project_name}/anatomy').content)['roots'][0][self.platform]
        self.project_root = os.path.join(self.project_root, self.project_name).replace('\\', os.path.sep).replace('/', os.path.sep)
        jsonFolderStruct = get_addons_project_settings(self.project_name)['core']['project_folder_structure']
        foldersDict = json.loads(jsonFolderStruct)
        self.log.debug(self.project_root)
        self.make_folders(self.find_traversals(foldersDict))
        return True

    def find_traversals(self,data, path=None, traversals=None):
        if path is None:
            path = []  # Initialize path for root call
        if traversals is None:
            traversals = []  # Initialize the list of traversals
        for key, value in data.items():
            current_path = path + [key]
            if isinstance(value, dict) and value:
                self.find_traversals(value, current_path, traversals)
            else:
                traversals.append(current_path)
        return traversals

    def make_folders(self,traversals):
        for traversal in traversals:
            #filter out ftrack entities
            traversal = [re.sub(self.pattern_ent_ftrack,"", folder) for folder in traversal]
            if any('[symlink.' in item for item in traversal):
                #if there are multiple symlinks in a traversal, it will only get the first one
                #so far, the only links are just after the project root to indicate different cross drive strucutres
                match = [item for item in traversal if '[symlink.' in item][0]
                drive_hint = match.split('.')[1].replace(']','')
                behind = traversal[:traversal.index(match)]
                drive_mapped_root = self.project_root.replace(self.drives[self.platform]['production'], self.drives[self.platform][drive_hint])
                cross_drive = [folder for folder in traversal if folder != match]
                cross_drive_rooted = list(map(lambda x: x.replace('__project_root__',
                                                      drive_mapped_root),cross_drive))
                behind_rooted = list(map(lambda x: x.replace('__project_root__', self.project_root), behind))
                os.makedirs(os.path.join(*behind_rooted), exist_ok=True)
                os.makedirs(os.path.join(*cross_drive_rooted), exist_ok=True)
                continue
            traversal_rooted = list(map(lambda x: x.replace('__project_root__', self.project_root), traversal))
            os.makedirs(os.path.join(*traversal_rooted))

def register(session):
    CreateHornetFolders(session).register()
