import os, json, csv


def subsystem_of(file_path):
    str_list = file_path.split('/')
    if len(str_list) == 1:
        return ''

    if str_list[0] == '':
        return str_list[1]
    return str_list[0]


class Profile:
    def __init__(self, data):
        self.account_id = data['_account_id']
        self.registered_on = data['registered_on']
        self.name = ''
        if 'name' in data.keys():
            self.name = data['name']

    @staticmethod
    def is_bot(project, name):
        project = project.lower()
        name = name.lower()
        if (project in name) or name == 'do not use':
            return True

        words = name.split()
        for word in ['bot', 'chatbot', 'ci', 'jenkins']:
            if word in words:
                return True

        return False


class File:
    def __init__(self, data, path):
        self.path = path
        self.name = os.path.basename(path)

        self.status = 'M'  # modified
        if 'status' in data.keys():
            self.status = data['status']  # 'A' added, 'D' deleted

        self.lines_inserted = 0
        if 'lines_inserted' in data.keys():
            self.lines_inserted = data['lines_inserted']
        self.size_delta = data['size_delta']
        self.size = data['size']

        self.lines_deleted = 0
        if 'lines_deleted' in data.keys():
            self.lines_deleted = data['lines_deleted']

        words = self.name.split('.')
        if len(words) > 1:
            self.type = words[-1]
        else:
            self.type = None


class Revision:
    def __init__(self, id, data):
        self.id = id
        self.number = data['_number']
        self.created = data['created']
        self.uploader = data['uploader']['_account_id']
        self.files = [File(data['files'][file_name], file_name) for file_name in data['files'].keys()]
        self.commit_message = data['commit']['subject']

    def __lt__(self, other):
        return self.number < other.number


class Label:
    def __init__(self, data, kind):
        self.kind = kind
        self.account_id = data['_account_id']

        if 'value' in data.keys():
            self.value = data['value']
        else:
            self.value = None
        if 'date' in data.keys():
            self.date = data['date']
        else:
            self.date = None


class Message:
    def __init__(self, data):
        if '_revision_number' in data.keys():
            self.revision_number = data['_revision_number']
        else:
            self.revision_number = None

        self.message = data['message']
        self.date = data['date']

        if 'real_author' in data.keys():
            self.author = data['real_author']['_account_id']
        elif 'author' in data.keys():
            self.author = data['author']['_account_id']
        self.tag = ''
        if 'tag' in data.keys():
            self.tag = data['tag']


class Change:
    def __init__(self, data):
        self.data = data
        self.project = data['project']
        self.change_number = data['_number']
        self.id = data['id']
        self.status = data['status']
        self.subject = data['subject']

        self.created = data['created']
        self.updated = data['updated']

        self.first_revision_cached = None
        self.revisions_cached = None
        self.labels_cached = None
        self.messages_cached = None
        self.reviewers_cached = None

    @property
    def owner(self):
        return self.data['owner']['_account_id']

    @property
    def first_revision(self):
        if self.first_revision_cached is not None:
            return self.first_revision_cached

        revisions = self.revisions
        if len(revisions) == 0:
            self.first_revision_cached = None
        else:
            self.first_revision_cached = revisions[0] # revisions are sorted by date

        return self.first_revision_cached

    @property
    def revisions(self):
        if self.revisions_cached is not None:
            return self.revisions_cached

        revisions_data = self.data["revisions"]
        revisions = []
        for revision_id in revisions_data.keys():
            revision = Revision(revision_id, revisions_data[revision_id])
            revisions.append(revision)

        self.revisions_cached = sorted(revisions, key=lambda x: x.number)
        return self.revisions_cached

    @property
    def labels(self):
        if self.labels_cached is not None:
            return self.labels_cached

        labels_data = self.data["labels"]
        labels = []
        for kind in labels_data.keys():
            if "all" not in labels_data[kind].keys():
                continue
            for label_data in labels_data[kind]["all"]:
                label = Label(label_data, kind)
                # 0 values aren't important
                if label.value != 0 and label.value is not None:
                    labels.append(label)

        self.labels_cached = sorted(labels, key=lambda x: x.date)
        return self.labels_cached

    @property
    def reviewers(self):
        if self.reviewers_cached is not None:
            return self.reviewers_cached
        reviewers = []
        if "reviewers" in self.data.keys():
            if "REVIEWER" in self.data["reviewers"].keys():
                for account in self.data["reviewers"]["REVIEWER"]:
                    reviewers.append(account["_account_id"])

        self.reviewers_cached = reviewers
        return reviewers

    @property
    def messages(self):
        if self.messages_cached is not None:
            return self.messages_cached

        messages = []
        for message_data in self.data['messages']:
            messages.append(Message(message_data))

        self.messages_cached = sorted(messages, key=lambda x: x.date)
        return self.messages_cached

    @property
    def is_mergeable(self):
        return self.data['mergeable']

    def is_work_in_progress(self):
        if 'work_in_progress' in self.data.keys():
            return self.data['work_in_progress']
        return False

    def is_real_change(self):
        first_revision = self.first_revision
        if first_revision is not None and len(first_revision.files) != 0:
            return True
        return False

    @property
    def files(self):
        first_revision = self.first_revision
        if first_revision is None:
            return []
        return first_revision.files

    @property
    def subsystems(self):
        subsystems = set()
        for file in self.files:
            if (file.lines_deleted + file.lines_inserted) > 0:
                subsystem = subsystem_of(file.path)
                if subsystem != '':
                    subsystems.add(subsystem)

        return subsystems

    @property
    def directories(self):
        directories = set()
        for f in self.files:
            if f.lines_inserted + f.lines_deleted > 0:
                directories.add(os.path.dirname(f.path))
        return directories

    @property
    def file_type_num(self):
        extensions = set()
        for f in self.files:
            if f.lines_inserted + f.lines_deleted == 0:
                continue

            extension = f.type
            if extension is not None:
                extensions.add(extension)
        return len(extensions)

    @property
    def language_num(self):
        languages = ['java', 'c', 'h', 'cxx', 'hxx', 'cpp', 'hpp', 'rb', 'py', 'javascript',
                     'bash', 'sh', 'go', 'html', 'php', ' js']
        extend_set = set()
        c_set = set()
        c_set.add('c')
        c_set.add('h')
        c_set.add('cxx')
        c_set.add('hxx')
        c_set.add('cpp')
        c_set.add('hpp')
        javascript = set()
        javascript.add('javascript')
        javascript.add('js')
        bash_set = set()
        bash_set.add('bash')
        bash_set.add('sh')
        for f in self.files:
            if f.lines_inserted + f.lines_deleted == 0:
                continue

            if f.type in languages:
                extend_set.add(f.type)

        if len(c_set & extend_set) > 0:
            extend_set -= c_set
            extend_set.add('c')
        if len(javascript & extend_set) > 0:
            extend_set -= javascript
            extend_set.add('js')
        if len(bash_set & extend_set) > 0:
            extend_set -= bash_set
            extend_set.add('bash')

        return len(extend_set)


class Comment:
    def __init__(self, data):
        self.author = data['author']['_account_id']
        self.patch_set = data['patch_set']
        self.id = data['id']
        self.line = data['line']

        self.in_reply_to = ''
        if 'in_reply_to' in data.keys():
            self.in_reply_to = data['in_reply_to']
        self.updated = data['updated']
        self.message = data['message']
        self.unresolved = data['unresolved']


def parse_comments(source, destination):
    output_file = open(os.path.join(destination, "comments.csv"), "w", newline='')
    writer = csv.writer(output_file, delimiter=',', dialect='excel')
    writer.writerow(['change_id', 'filename', 'author', 'patch_set', 'id', 'line',
                     'in_reply_to', 'updated', 'message', 'unresolved'])

    filenames = [filename for filename in os.listdir(source)]
    for filename in filenames:
        change_id = filename.split('.')[0].split('_')[1]
        comment_jsons = json.load(open(os.path.join(source, filename), "r"))
        for name in comment_jsons.keys():
            comment_json = comment_jsons[name]
            comment = Comment(comment_json)
            writer.writerow([change_id, filename, comment.author, comment.patch_set, comment.id, comment.line,
                             comment.in_reply_to, comment.updated, comment.message, comment.unresolved])
    output_file.close()