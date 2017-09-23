import unittest
import json
from StringIO import StringIO
from ghtool import *


class GhtoolTest(unittest.TestCase):
    def setUp(self):
        self.output_stream = StringIO()
        self.error_stream = StringIO()
        self.ghtool = Ghtool(output_stream=self.output_stream, error_stream=self.error_stream)

    def assertExitCode(self, exit_code, callable, *args, **kwargs):
        with self.assertRaises(SystemExit) as cm:
            callable(*args, **kwargs)
        self.assertEqual(cm.exception.code, exit_code)

    def test_list_nofilter(self):
        self.ghtool.main(["list"])
        json_output = json.loads(self.output_stream.getvalue())
        # Assert that DEFAULT_COUNT repositories were returned
        self.assertEqual(len(json_output), DEFAULT_COUNT)

    def test_list_python(self):
        self.ghtool.main(["list", "python"])
        json_output = json.loads(self.output_stream.getvalue())
        self.assertEqual(len(json_output), DEFAULT_COUNT)
        # Assert that the returned repositories are indeed in Python
        for repo in json_output:
            self.assertEqual(repo["language"], "Python")

    def test_list_python_count(self):
        # Try different counts
        TEST_COUNTS = [1, 7, MAX_COUNT]
        for count in TEST_COUNTS:
            self.setUp()
            self.ghtool.main(["list", "python", "-n", str(count)])
            json_output = json.loads(self.output_stream.getvalue())
            # Assert that the number of returned repositories is correct
            self.assertEqual(len(json_output), count)

    def test_desc(self):
        # Two well-known GitHub repositories: Twitter Bootstrap and gitignore templates.
        self.ghtool.main(["desc", "2126244", "1062897"])
        json_output = json.loads(self.output_stream.getvalue())
        self.assertEqual(len(json_output), 2)
        self.assertEqual(json_output[0]["id"], 2126244)
        self.assertEqual(json_output[0]["full_name"], "twbs/bootstrap")

        self.assertEqual(json_output[1]["id"], 1062897)
        self.assertEqual(json_output[1]["full_name"], "github/gitignore")

    def test_desc_notfound(self):
        # Repository with id==2 does not exist.
        self.assertExitCode(ExitCodes.GITHUB_RESOURCE_NOT_FOUND, self.ghtool.main, ["desc", "1", "2", "3"])
        # Assert nothing was printed to standard output
        self.assertEqual(self.output_stream.getvalue(), "")

    def test_invalid_args(self):
        # Invalid arguments
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, [])
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, ["aaaaaa"])
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, ["-aaaaaa"])
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, ["list", "-aaaaaa"])
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, ["desc", "aaaaaa"])
        self.assertExitCode(ExitCodes.INVALID_ARGS, self.ghtool.main, ["desc", "2126244", "-aaaaaa"])

        # Out-of-bounds count
        self.assertExitCode(ExitCodes.INVALID_ARG_VALUES, self.ghtool.main, ["list", "-n", "0"])
        self.assertExitCode(ExitCodes.INVALID_ARG_VALUES, self.ghtool.main, ["list", "-n", str(MAX_COUNT + 1)])
        self.assertExitCode(ExitCodes.INVALID_ARG_VALUES, self.ghtool.main, ["list", "python", "-n", "0"])
        self.assertExitCode(ExitCodes.INVALID_ARG_VALUES, self.ghtool.main,
                            ["list", "python", "-n", str(MAX_COUNT + 1)])

        # Non-existent language
        self.assertExitCode(ExitCodes.INVALID_ARG_VALUES, self.ghtool.main, ["list", "fakelanguage123"])

if __name__ == "__main__":
    unittest.main()