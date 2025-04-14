"""
A metaclass to register classes that offer alternative implementations of things.

There are probably a bunch of packages which do this, here's two:
https://py-class-pool.readthedocs.io/en/latest/index.html
https://github.com/epwalsh/python-registrable

But the core logic is simple and we want two features not implemented by those packages,
selective registration based on DeployType, and preferred / controlled order of
registered classes.
"""


class Registerable(type):
    """Metaclass for classes that can register themselves in a list.

    Needs to be a metaclass because each base-class of registerables needs its own, not
    inherited, list of classes.  And if we're going to use a metaclass, might as well do
    auto-registration, although still need to ensure class def's are imported to be
    registered.
    """

    @classmethod
    def tree_root(cls, bases):
        """Find the base class in bases that is Registerable but has not Registerable
        parent."""
        for base in bases:
            if base.__class__ == cls and all(
                i.__class__ != cls for i in base.__bases__
            ):
                return base

        for base in bases:
            if found := cls.tree_root(base.__bases__):
                return found

        return None

    def __new__(
        cls,
        clsname,
        bases,
        attrs,
        _reg_id=None,  # use class name if None
        _reg_class="_reg_class",
        _reg_order=None,
    ):
        """See main for usage."""
        if all(i.__class__ != cls for i in bases):
            # This is the root of the tree.
            attrs[_reg_class] = {}
            attrs["_reg_meta"] = {  # only passed to root, so save
                "id": _reg_id,
                "class": _reg_class,
                "order": _reg_order,
            }
            return type.__new__(cls, clsname, bases, attrs)

        # Find the base for this class that is Registerable with no Registerable
        # parent, and register there.
        root = cls.tree_root(bases)
        new_class = type.__new__(cls, clsname, bases, attrs)
        if hasattr(root, "_reg_check_register"):
            allowed = root._reg_check_register(new_class)
        else:
            allowed = True
        if allowed:  # registration takes place here
            getattr(root, root._reg_meta["class"])[
                attrs.get(root._reg_meta["id"], clsname)
            ] = new_class
            if root._reg_meta["order"]:
                cls.order_classes(root)
        # It exists in the module where it was defined, but may not be registered.
        return new_class

    @classmethod
    def order_classes(cls, root):
        """Sort classes to match preferred ordering."""
        order = getattr(root, root._reg_meta["order"])
        if not order:
            return
        dict_ = getattr(root, root._reg_meta["class"])
        not_in_list = {key: val for key, val in dict_.items() if key not in order}

        in_list = {k: dict_[k] for k in order if k in dict_}
        dict_.clear()
        dict_.update(in_list)
        dict_.update(not_in_list)


def main():
    """Test code / documentation."""

    class PageRenederer(
        metaclass=Registerable,
        _reg_id="renderer_id",
        _reg_class="renderers",
        _reg_order="renderer_order",
    ):
        # List default and user renderers before alphabetical listing of others.  This
        # requires pre-existing knowledge of renderers that might be registered, which
        # is ok for some workflows.
        renderer_order = ["user", "default"]

        @classmethod
        def _reg_check_register(cls, renderer):
            """Checker that renderer should be registered."""
            # getattr just to allow CompactRenderer to demo default name
            return getattr(renderer, "renderer_id", "good") != "bad"

    class CompactRenderer(PageRenederer):
        pass  # id will default to class name.

    class UserRenderer(PageRenederer):
        renderer_id = "user"

    class User2Renederer(UserRenderer):  # inheritance is fine
        renderer_id = "user_2"

    class BadRenderer(PageRenederer):
        renderer_id = "bad"

    class DefaultRenderer(PageRenederer):
        renderer_id = "default"

    for k, v in PageRenederer.renderers.items():
        print(f"{k:>18s}: {v}")

    # note ordering and absence of BadRenderer
    #             user: <class '__main__.main.<locals>.UserRenderer'>
    #          default: <class '__main__.main.<locals>.DefaultRenderer'>
    #  CompactRenderer: <class '__main__.main.<locals>.CompactRenderer'>
    #           user_2: <class '__main__.main.<locals>.User2Renederer'>


if __name__ == "__main__":
    main()
