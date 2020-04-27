from zipfile import ZipFile 
import os 
  
def get_all_file_paths(directory): 
  
    # initializing empty file paths list 
    file_paths = [] 
  
    # crawling through directory and subdirectories 
    for root, directories, files in os.walk(directory): 
        for filename in files: 
            # join the two strings in order to form the full filepath. 
            filepath = os.path.join(root, filename) 
            file_paths.append(filepath) 
  
    # returning all file paths 
    return file_paths        

def compress(name, files):
    zip_name = '/tmp/{}.zip'.format(name)
    # use snake case
    with ZipFile(zip_name, 'w') as zip: 
        # writing each file one by one 
        for file in files: 
            zip.write(file, os.path.basename(file)) 
        zip.close()

    return zip_name

def decompress(zip_path):
    zip_file_name = '{}.zip'.format(zip_path)
    with ZipFile(zip_file_name, 'r') as obj:
        obj.extractall(path=zip_path)
    # remove original zip
    os.remove(zip_file_name)

