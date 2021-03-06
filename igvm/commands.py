"""igvm - Command Routines

Copyright (c) 2018, InnoGames GmbH
"""

import logging

from fabric.colors import green, red, white, yellow
from fabric.network import disconnect_all

from igvm.exceptions import InvalidStateError
from igvm.host import with_fabric_settings
from igvm.utils.units import parse_size
from igvm.vm import VM

log = logging.getLogger(__name__)


def _check_defined(vm, fail_hard=True):
    error = None

    if not vm.hypervisor:
        error = ('"{}" has no hypervisor defined. Use --force to ignore this'
                 .format(vm.fqdn))
    elif not vm.hypervisor.vm_defined(vm):
        error = ('"{}" is not built yet or is not running on "{}"'
                 .format(vm.fqdn, vm.hypervisor.fqdn))

    if error:
        if fail_hard:
            raise InvalidStateError(error)
        else:
            log.info(error)


@with_fabric_settings
def vcpu_set(vm_hostname, count, offline=False, ignore_reserved=False):
    """Change the number of CPUs in a VM"""
    vm = VM(vm_hostname, ignore_reserved=ignore_reserved)
    _check_defined(vm)

    if offline and not vm.is_running():
        log.info(
            '"{}" is already powered off, ignoring --offline.'
            .format(vm.fqdn)
        )
        offline = False

    if count == vm.dataset_obj['num_cpu']:
        raise Warning('CPU count is the same.')

    if offline:
        vm.shutdown()
    vm.set_num_cpu(count)
    if offline:
        vm.start()


@with_fabric_settings
def mem_set(vm_hostname, size, offline=False, ignore_reserved=False):
    """Change the memory size of a VM

    Size argument is a size unit, which defaults to MiB.
    The plus (+) and minus (-) prefixes are allowed to specify a relative
    difference in the size.  Reducing memory is only allowed while the VM is
    powered off.
    """
    vm = VM(vm_hostname, ignore_reserved=ignore_reserved)
    _check_defined(vm)

    if size.startswith('+'):
        new_memory = vm.dataset_obj['memory'] + parse_size(size[1:], 'm')
    elif size.startswith('-'):
        new_memory = vm.dataset_obj['memory'] - parse_size(size[1:], 'm')
    else:
        new_memory = parse_size(size, 'm')

    if new_memory == vm.dataset_obj['memory']:
        raise Warning('Memory size is the same.')

    if offline and not vm.is_running():
        log.info(
            '"{}" is already powered off, ignoring --offline.'
            .format(vm.fqdn)
        )
        offline = False

    if offline:
        vm.shutdown()
    vm.set_memory(new_memory)
    if offline:
        vm.start()


@with_fabric_settings
def disk_set(vm_hostname, size, ignore_reserved=False):
    """Change the disk size of a VM

    Currently only increasing the disk is implemented.  Size argument is
    allowed as text, but it must always be in GiBs without a decimal
    place.  The plus (+) and minus (-) prefixes are allowed to specify
    a relative difference in the size.  Of course, minus is going to
    error out.
    """
    vm = VM(vm_hostname, ignore_reserved=ignore_reserved)
    _check_defined(vm)

    current_size_gib = vm.dataset_obj['disk_size_gib']
    if size.startswith('+'):
        new_size_gib = current_size_gib + parse_size(size[1:], 'g')
    elif size.startswith('-'):
        new_size_gib = current_size_gib - parse_size(size[1:], 'g')
    else:
        new_size_gib = parse_size(size, 'g')

    if new_size_gib == vm.dataset_obj['disk_size_gib']:
        raise Warning('Disk size is the same.')

    vm.hypervisor.vm_set_disk_size_gib(vm, new_size_gib)

    vm.dataset_obj['disk_size_gib'] = new_size_gib
    vm.dataset_obj.commit()


@with_fabric_settings
def vm_build(vm_hostname, localimage=None, nopuppet=False, postboot=None,
             ignore_reserved=False):
    """Create a VM and start it

    Puppet in run once to configure baseline networking.
    """

    vm = VM(vm_hostname)

    # Could also have been set in serveradmin already.
    if not vm.hypervisor:
        vm.set_best_hypervisor(
            ['online', 'online_reserved'] if ignore_reserved else ['online']
        )

    vm.build(
        localimage=localimage,
        runpuppet=not nopuppet,
        postboot=postboot,
    )


@with_fabric_settings
def vm_rebuild(vm_hostname, force=False):
    """Destroy and reinstall a VM"""
    vm = VM(vm_hostname, ignore_reserved=True)
    _check_defined(vm)

    if vm.is_running():
        if force:
            vm.hypervisor.stop_vm_force(vm)
        else:
            raise InvalidStateError('"{}" is still running.'.format(vm.fqdn))

    vm.hypervisor.delete_vm(vm)
    vm.build()


@with_fabric_settings
def vm_start(vm_hostname):
    """Start a VM"""
    vm = VM(vm_hostname)
    _check_defined(vm)

    if vm.is_running():
        log.info('"{}" is already running.'.format(vm.fqdn))
        return
    vm.start()


@with_fabric_settings
def vm_stop(vm_hostname, force=False):
    """Gracefully stop a VM"""
    vm = VM(vm_hostname)
    _check_defined(vm)

    if not vm.is_running():
        log.info('"{}" is already stopped.'.format(vm.fqdn))
        return
    if force:
        vm.hypervisor.stop_vm_force(vm)
    else:
        vm.shutdown()
    log.info('"{}" is stopped.'.format(vm.fqdn))


@with_fabric_settings
def vm_restart(vm_hostname, force=False, no_redefine=False):
    """Restart a VM

    The VM is shut down and recreated, using the existing disk. This can be
    useful to discard temporary changes or adapt new hypervisor optimizations.
    No data will be lost.
    """
    vm = VM(vm_hostname, ignore_reserved=True)
    _check_defined(vm)

    if not vm.is_running():
        raise InvalidStateError('"{}" is not running'.format(vm.fqdn))

    if force:
        vm.hypervisor.stop_vm_force(vm)
    else:
        vm.shutdown()

    if not no_redefine:
        vm.hypervisor.redefine_vm(vm)

    vm.start()
    log.info('"{}" is restarted.'.format(vm.fqdn))


@with_fabric_settings
def vm_delete(vm_hostname, force=False, retire=False):
    """Delete the VM from the hypervisor and from serveradmin

    If force is True the VM will be deleted even though it is still running on
    its hypervisor. Furthermore force will delete the serveradmin object, even
    if the VM doesn't have a hypervisor set in serveradmin or it has not yet
    been created on the defined hypervisor.

    If retire is True the VM will not be deleted from serveradmin but it's
    state will be updated to 'retired'.
    """

    vm = VM(vm_hostname, ignore_reserved=True)
    # Make sure the VM has a hypervisor and that it is defined on it.
    # Abort if the VM has not been defined and force is not True.
    _check_defined(vm, fail_hard=not force)

    # Make sure the VM is shut down.
    # Abort if the VM is not shut down and force is not True.
    if vm.hypervisor and vm.hypervisor.vm_defined(vm) and vm.is_running():
        if force:
            vm.hypervisor.stop_vm_force(vm)
        else:
            raise InvalidStateError('"{}" is still running.'.format(vm.fqdn))

    # Delete the VM from its hypervisor if required.
    if vm.hypervisor and vm.hypervisor.vm_defined(vm):
        vm.hypervisor.delete_vm(vm)

    # Delete the serveradmin object of this VM
    # or update its state to 'retired' if retire is True.
    if retire:
        vm.dataset_obj['state'] = 'retired'
        vm.dataset_obj.commit()
        log.info(
            '"{}" is destroyed and set to "retired" state.'
            .format(vm.fqdn)
        )
    else:
        vm.dataset_obj.delete()
        vm.dataset_obj.commit()
        log.info(
            '"{}" is destroyed and deleted from Serveradmin'
            .format(vm.fqdn)
        )


@with_fabric_settings
def vm_sync(vm_hostname):
    """Synchronize VM resource attributes to Serveradmin

    This command collects actual resource allocation of a VM from the
    hypervisor and overwrites outdated attribute values in Serveradmin."""
    vm = VM(vm_hostname, ignore_reserved=True)
    _check_defined(vm)

    attributes = vm.hypervisor.vm_sync_from_hypervisor(vm)
    changed = []
    for attrib, value in attributes.iteritems():
        current = vm.dataset_obj[attrib]
        if current == value:
            log.info('{}: {}'.format(attrib, current))
            continue
        log.info('{}: {} -> {}'.format(attrib, current, value))
        vm.dataset_obj[attrib] = value
        changed.append(attrib)
    if changed:
        vm.dataset_obj.commit()
        log.info(
            '"{}" is synchronized {} attributes ({}).'
            .format(vm.fqdn, len(changed), ', '.join(changed))
        )
    else:
        log.info(
            '"{}" is already synchronized on Serveradmin.'.format(vm.fqdn)
        )


@with_fabric_settings
def host_info(vm_hostname):
    """Extract runtime information about a VM

    Library consumers should use VM.info() directly.
    """
    vm = VM(vm_hostname, ignore_reserved=True)

    info = vm.info()

    # Disconnect fabric now to avoid messages after the table
    disconnect_all()

    categories = (
        ('General', (
            'hypervisor',
            'status',
        )),
        ('Network', (
            'intern_ip',
            'mac_address',
        )),
        ('Resources', (
            'num_cpu',
            'max_cpus',
            'memory',
            'memory_free',
            'max_mem',
            'disk',
            'disk_size_gib',
            'disk_free_gib',
        )),
        # Anything else will appear in this section
        ('Other', None),
    )

    def _progress_bar(free_key, capacity_key, result_key, unit):
        """Helper to show nice progress bars."""
        if free_key not in info or capacity_key not in info:
            return
        free = info[free_key]
        del info[free_key]
        capacity = info[capacity_key]
        del info[capacity_key]

        simple_stats = (
            'Current: {} {unit}\n'
            'Free:    {} {unit}\n'
            'Max:     {} {unit}'
            .format(capacity - free, free, capacity, unit=unit)
        )

        if not 0 <= free <= capacity > 0:
            log.warning(
                '{} ({}) and {} ({}) have weird ratio, skipping progress '
                'calculation'
                .format(free_key, free, capacity_key, capacity)
            )
            info[result_key] = red(simple_stats)
            return

        assert free >= 0 and free <= capacity
        ratio = 1 - float(free) / float(capacity)
        if ratio >= 0.9:
            color = red
        elif ratio >= 0.8:
            color = yellow
        else:
            color = green

        max_bars = 20
        num_bars = int(round(ratio * max_bars))
        info[result_key] = (
            '[{}{}] {}%\n{}'
            .format(
                color('#' * num_bars), ' ' * (max_bars - num_bars),
                int(round(ratio * 100)),
                simple_stats,
            )
        )

    _progress_bar('memory_free', 'memory', 'memory', 'MiB')
    _progress_bar('disk_free_gib', 'disk_size_gib', 'disk', 'GiB')

    max_key_len = max(len(k) for k in info.keys())
    for category, keys in categories:
        # Handle 'Other' section by defaulting to all keys
        keys = keys or info.keys()

        # Any info available for the category?
        if not any(k in info for k in keys):
            continue

        print('')
        print(white(category, bold=True))
        for k in keys:
            if k not in info:
                continue

            # Properly re-indent multiline values
            value = str(info.pop(k))
            value = ('\n' + ' ' * (max_key_len + 3)).join(value.splitlines())
            print('{} : {}'.format(k.ljust(max_key_len), value))


@with_fabric_settings
def vm_rename(vm_hostname, new_hostname, offline=False):
    """Redefine the VM on the same hypervisor with a different name

    We can only do this operation offline.  If the VM is online, it needs
    to be shut down.  No data will be lost.
    """

    vm = VM(vm_hostname, ignore_reserved=True)
    _check_defined(vm)

    if not offline:
        raise NotImplementedError(
            'Rename command only works with --offline at the moment.'
        )
    if not vm.is_running():
        raise NotImplementedError(
            'Rename command only works online at the moment.'
        )

    vm.rename(new_hostname)
