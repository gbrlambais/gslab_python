import unittest
import sys
import os
import re
import mock
from StringIO import StringIO

# Ensure that Python can find and load the GSLab libraries
os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append('../..')

import gslab_scons
import gslab_scons.size_warning as sw
from gslab_scons._exception_classes import ReleaseError
from gslab_make.tests import nostderrout


class TestSizeWarning(unittest.TestCase):
    @mock.patch('gslab_scons.size_warning.sys.stdout', new_callable = StringIO)
    @mock.patch('gslab_scons.size_warning.create_size_dictionary')
    @mock.patch('gslab_scons.size_warning.list_ignored_files')
    def test_issue_size_warnings(self, 
                                 mock_list_ignored, 
                                 mock_create_dict,
                                 mock_stdout):
        bytes_in_MB = 1000000
        big_size = 3
        small_size = 1
        total_size = big_size + small_size
        mock_create_dict.return_value = {'large.txt':   big_size*bytes_in_MB,
                                         'small.txt': small_size*bytes_in_MB}
        mock_list_ignored.return_value = ['large.txt']

        look_in = ['.']

        # Neither file over limit
        sw.issue_size_warnings(look_in,
                               file_MB_limit  = big_size + 0.1, 
                               total_MB_limit = big_size + 0.1)
        # We test the function by mocking sys.stdout with a StringIO object.
        # Here, the getvalue() method prints all standard output generated by
        # gslab_scons.size_warning.
        self.assertEqual('', mock_stdout.getvalue())

        # Only ignored filed over limit
        sw.issue_size_warnings(look_in,
                               file_MB_limit  = big_size - 0.1, 
                               total_MB_limit = big_size + 0.1)
        self.assertEqual('', mock_stdout.getvalue())

        # Ignored file no longer ignored
        mock_list_ignored.return_value = []

        sw.issue_size_warnings(look_in,
                               file_MB_limit  = big_size - 0.1, 
                               total_MB_limit = total_size + 0.1)

        look_for = ["Warning:", 
                   "large.txt \(size: %d\.00 MB\)" % big_size]
        for item in look_for:
            self.assertTrue(re.search(item, mock_stdout.getvalue()))
        # Refresh mocked standard output
        mock_stdout.buflist = []
        mock_stdout.buf = ''

        # Both files over limit
        mock_list_ignored.return_value = []
        sw.issue_size_warnings(look_in,
                               file_MB_limit  = small_size - 0.1, 
                               total_MB_limit = total_size + 0.1)
        message = 'Versioning files of this size is discouraged.\n'
        # Use buflist, a list of messages printed to stdout, to check that
        # issue_size_warnings printed warnings as expected.
        self.assertEqual(mock_stdout.buflist.count(message), 2)
        mock_stdout.buflist = []
        mock_stdout.buf = ''

        # No file over limit, but total size over limit
        sw.issue_size_warnings(look_in,
                               file_MB_limit  = big_size + 0.1, 
                               total_MB_limit = total_size - 0.1)
        message = 'Versioning this much content is discouraged.\n'
        self.assertIn(message, mock_stdout.buflist)
        mock_stdout.buflist = []
        mock_stdout.buf = ''

        # Large file over limit and total size over limit
        sw.issue_size_warnings(look_in,
                               file_MB_limit = big_size - 0.1, 
                               total_MB_limit = total_size - 0.1)
        file_warning  = 'Versioning files of this size is discouraged.\n'
        total_warning = 'Versioning this much content is discouraged.\n'
        self.assertIn(file_warning,  mock_stdout.buflist)
        self.assertIn(total_warning, mock_stdout.buflist)

    def test_red_and_bold(self):
        '''
        Test that _red_and_bold() adds characters to its argument
        as expected'''
        text = 'test'
        self.assertEqual('\033[91m\033[1m%s\033[0m' % text, 
                         sw._red_and_bold(text))

    def test_is_subpath(self):
        expect_true = [{'inner': '.',              'outer': '..'},
                       {'inner': 'release',        'outer': '.'},
                       {'inner': 'release',        'outer': ''}, 
                       {'inner': './release',      'outer': '.'},
                       {'inner': 'release',        'outer': '/'},
                       {'inner': 'release/subdir', 'outer': '.'},
                       {'inner': 'release/subdir', 'outer': 'release'},
                       {'inner': 'release/subdir', 'outer': './release'},
            {'inner': 'release/../release/subdir', 'outer': 'release'}]

        expect_false = [{'inner': '.',        'outer': 'release'},
                        {'inner': '/release', 'outer': '.'}]

        for keywords in expect_true:
            self.assertTrue(sw._is_subpath(**keywords))
        for keywords in expect_false:
            print keywords
            self.assertFalse(sw._is_subpath(**keywords))   

    @mock.patch('gslab_scons.size_warning.os.path.isfile')
    @mock.patch('gslab_scons.size_warning.os.path.isdir')
    @mock.patch('gslab_scons.size_warning.os.walk')
    @mock.patch('gslab_scons.size_warning.subprocess.check_output')
    def test_list_ignored_files(self, mock_check, mock_walk,
                                mock_isdir, mock_isfile):
        mock_check.side_effect  = check_ignored_side_effect('standard')
        mock_walk.side_effect   = make_walk_side_effect('list_ignored_files')
        mock_isdir.side_effect  = isdir_ignored_side_effect
        mock_isfile.side_effect = isfile_ignored_side_effect

        # Multiple directories
        look_in = ['raw', 'release']
        ignored = sw.list_ignored_files(look_in)
        expect_ignored = ['raw/large_file.txt', 'release/.DS_Store', 
                          'release/subdir/ignored.txt']

        self.assertEqual(len(ignored), len(expect_ignored))
        for i in range(len(ignored)):
            self.assertIn(ignored[i], expect_ignored)

        # One directory
        look_in = ['raw']
        ignored = sw.list_ignored_files(look_in)
        expect_ignored = ['raw/large_file.txt']

        self.assertEqual(len(ignored), len(expect_ignored))
        self.assertEqual(ignored[0], expect_ignored[0])       

        # The root
        look_in = ['.']
        ignored = sw.list_ignored_files(look_in)
        expect_ignored = ['root_ignored.txt',  'raw/large_file.txt',
                          'release/.DS_Store', 'release/subdir/ignored.txt']
        self.assertEqual(len(ignored), len(expect_ignored))
        for i in range(len(ignored)):
            self.assertEqual(ignored[i], expect_ignored[i])          

        # Test that list_ignored_files returns an empty list when 
        # git is not ignoring any files.
        mock_check.side_effect  = check_ignored_side_effect(ignored = 'none')
        ignored = sw.list_ignored_files(look_in)

        self.assertIsInstance(ignored, list)
        self.assertEqual(len(ignored), 0)

    @mock.patch('gslab_scons.size_warning.os.path.getsize')
    @mock.patch('gslab_scons.size_warning.os.walk')
    @mock.patch('gslab_scons.size_warning.os.path.isdir')
    def test_create_size_dictionary(self, mock_isdir, mock_walk, mock_getsize):
        '''
        Test that create_size_dictionary() correctly reports
        files' sizes in bytes.
        '''
        # Assign side effects
        mock_isdir.side_effect   = isdir_dict_side_effect        
        mock_walk.side_effect    = make_walk_side_effect('create_size_dictionary')
        mock_getsize.side_effect = getsize_dict_side_effect 

        # Test when one directory is provided
        sizes = sw.create_size_dictionary(['test_files'])

        self.assertEqual(len(sizes), 3)

        # Check that root_file.txt and test.pdf are in the dictionary
        root_path = [k for k in sizes.keys() if re.search('root_file.txt$', k)]
        pdf_path  = [k for k in sizes.keys() if re.search('test.pdf$', k)]
        self.assertTrue(len(root_path) > 0)
        self.assertTrue(len(pdf_path) > 0)

        # Check that the size dictionary reports these files' correct sizes in bytes
        self.assertEqual(sizes[root_path[0]], 100)
        self.assertEqual(sizes[pdf_path[0]], 1000)

        # Check when two directories are provided
        sizes = sw.create_size_dictionary(['test_files', 'release'])
        self.assertEqual(len(sizes), 4)
        path = [k for k in sizes.keys() if re.search('output.txt$', k)]
        self.assertTrue(len(path) > 0)
        self.assertEqual(sizes[path[0]], 16)

        # Check when '.' is provided
        sizes = sw.create_size_dictionary(['.'])
        self.assertEqual(len(sizes), 4)

        # Check that the function does not raise an error when its path argument
        # is not a directory.
        sizes = sw.create_size_dictionary(['nonexistent_directory'])
        self.assertEqual(sizes, dict())
        
        # The path argument must be a string
        with self.assertRaises(TypeError), nostderrout():
            sizes = sw.create_size_dictionary([10])


#== Side effects for testing list_ignored_files() ===
# Define the mock file structure for testing list_ignored_files()
struct = {'.': ['untracked.txt', 'make.log', 'root_ignored.txt'],
         'raw': ['large_file.txt', 'small_file.txt'], 
         'release': ['output.txt', '.DS_Store'],
         'release/subdir': ['ignored.txt']}

def check_ignored_side_effect(ignored = 'standard'):

    def effect(*args, **kwargs):
        '''Mock subprcess.check_output() for testing list_ignored_files()'''
    
        # Define mock messages from "git status --ignored"
        # i) Some files are ignored
        standard = \
            ['On branch testing\n',
             'Your branch is up-to-date with \'origin/testing\'.\n',
             'Changes not staged for commit:\n',
             '  (use "git add/rm <file>..." to update what will be committed)\n',
             '  (use "git checkout -- <file>..." to discard changes in working directory)\n',
             '\n',
             '\tmodified:   make.log\n',
             '\n',
             'Untracked files:\n',
             '  (use "git add <file>..." to include in what will be committed)\n',
             '\n',
             '\tuntracked.txt',
             '\n',
             'Ignored files:\n',
             '  (use "git add -f <file>..." to include in what will be committed)\n',
             '\n',
             '\troot_ignored.txt\n'
             '\traw/large_file.txt\n',
             '\trelease/.DS_Store\n',
             '\trelease/subdir/'
             '\n',
             '\n',
             'It took 2.44 seconds to enumerate untracked files. \'status -uno\'\n',
             'may speed it up, but you have to be careful not to forget to add\n',
             'new files yourself (see \'git help status\').\n',
             'no changes added to commit (use "git add" and/or "git commit -a")\n']
        
        # ii) No files are ignored
        none_ignored = \
            ['On branch issue59-size_warnings\n',
             'Your branch is up-to-date with \'origin/issue59-size_warnings\'.\n',
             'nothing to commit, working tree clean\n']

        if ignored == 'none':
            message = ''.join(none_ignored)
        else:
            message = ''.join(standard)

        command = args[0]
        if 'shell' in kwargs.keys():
            if kwargs['shell'] and (command == 'git status --ignored'):
                return message
    
        return None

    return effect


def make_walk_side_effect(test_type):
    '''
    Make os.walk() for one of the mock directory structures
      - Used in test_list_ignored_files() or
      - Used in test_create_size_dictionary()
    '''
    def side_effect(*args, **kwargs):
        path = args[0]
        path = os.path.relpath(path)
    
        if test_type == 'list_ignored_files':
            if path not in struct.keys():
                raise StopIteration
      
            # os.walk() generates a 3-tuple for each directory under the path passed
            # as its argument. The tuple is:
            #   (directory, [subdirectories], [files in root of directory])
            # Below, roots are the directories, `directories` is
            roots       = struct.keys()
            directories = map(lambda r: [d for d in roots if \
                                         sw._is_subpath(d, r) and d != r], roots)
            files       = [struct[r] for r in roots]

        elif test_type == 'create_size_dictionary':
            roots       = ['test_files',      'test_files/size_test',   'release']
            directories = [['size_test'],     [],                       []]
            files       = [['root_file.txt'], ['test.txt', 'test.pdf'], ['output.txt']]
        else:
            raise Exception('Invalid test_type specified.')

        for i in range(len(roots)):
            # Ensure info only provided about directory specified 
            # by os.walk()'s argument
            if sw._is_subpath(roots[i], path):
                yield (roots[i], directories[i], files[i])

    return side_effect 


def isdir_ignored_side_effect(*args, **kwargs):
    path = args[0]
    if path == '':
        return False
        
    isdir = (os.path.relpath(path) in struct.keys())
    return isdir


def isfile_ignored_side_effect(*args, **kwargs):
    path = args[0]
    if path == '':
        return False

    file_list = []

    for k in struct.keys():
        file_list += [os.path.join(k, f) for f in struct[k]]

    isfile = (os.path.relpath(path) in map(os.path.relpath, file_list))
    return isfile


#== Side effects for testing create_size_dictionary() ===
# These functions mock two directories containing files of various sizes
# and a system that does not recognises any other directories.
def isdir_dict_side_effect(*args, **kwargs):
    '''
    Mock os.path.isdir() so that it only recognises a few mocked directories
    as existing directories.
    '''
    path = args[0]
    if not isinstance(path, str):
        raise TypeError('coercing to Unicode: need string or buffer, '
                        '%s found' % type(path))
    acceptable = ['test_files', 'test_files/size_test', 'release', '.']
    return os.path.normpath(path) in acceptable


def getsize_dict_side_effect(*args, **kwargs):
    '''
    Mock os.path.getsize() to return sizes of files in mocked  directories.
    '''
    path = args[0]
    if path == 'test_files/root_file.txt':
        size = 100
    elif path == 'test_files/size_test/test.txt':
        size = 200
    elif path == 'test_files/size_test/test.pdf':
        size = 1000
    elif path == 'release/output.txt':
        size = 16
    else:
        raise OSError("[Errno 2] No such file or directory: '%s'" % path)

    return size


if __name__ == '__main__':
    unittest.main()