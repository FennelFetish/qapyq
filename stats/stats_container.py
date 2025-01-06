
from PySide6 import QtWidgets
from .stats_tags import TagStats
from .stats_imgsize import ImageSizeStats

# Count of unique tags
# Frequency of each tag
# Distribution of number of tags per image
# Top N most frequent tags
# Tag co-occurrence matrix
# Histogram of image counts by tag frequency
# Entropy of tag distribution

# Entropy measures the diversity or randomness of tag distribution in your dataset.
# A higher entropy indicates a more diverse distribution of tags, meaning that no single tag is overwhelmingly dominant.
# Conversely, lower entropy suggests that a few tags are used much more frequently than others.
# In the context of your image dataset, entropy can help you understand how evenly distributed your tags are across images.


# Apply filter to FileList (Gallery):
#   - Contains tag/string
#   - Tag/string is missing
#   - Caption/Tag property is empty

class StatsContainer(QtWidgets.QTabWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab

        self.tagStats = TagStats(tab)
        self.imageSizeStats = ImageSizeStats(tab)

        self.addTab(self.tagStats, "Tag Count")
        self.addTab(self.imageSizeStats, "Image Size")
