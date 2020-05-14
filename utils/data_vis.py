import io

import matplotlib.pyplot as plt


def gen(guild, status_type):
    return len([m for m in guild.members if str(m.status) == status_type])


class StatusChart:
    # Pie chart, where the slices will be ordered and plotted counter-clockwise:
    def __init__(self, guild, labels: list, sizes: list, colors: list):
        self.guild = guild
        self.labels = labels
        self.sizes = sizes
        self.colors = colors

    def make_pie(self):
        fig1, ax1 = plt.subplots(figsize=(5, 5))
        ax1.pie(self.sizes, autopct='%1.1f%%', colors=self.colors, startangle=90)
        ax1.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        title_obj = plt.title(f'Statuses for {self.guild}')
        plt.setp(title_obj, color='w')
        plt.legend(self.labels, loc="upper right")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        data = buf.read()
        return data


def bar_make(
        value: int, gap: int, *,
        fill: str = '█', empty: str = ' ',
        point: bool = False, length: int = 10):
    bar = ''

    percentage = (value/gap) * length

    if point:
        for i in range(0, length + 1):
            if i == round(percentage):
                bar += fill
            else:
                bar += empty
        return bar

    for i in range(1, length + 1):
        if i <= percentage:
            bar += fill
        else:
            bar += empty
    return bar
