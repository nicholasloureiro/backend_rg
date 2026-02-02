from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


class BaseModel(models.Model):
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="created_%(class)s",
    )
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="updated_%(class)s",
    )
    date_updated = models.DateTimeField(null=True, blank=True)
    canceled_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="canceled_%(class)s",
    )
    date_canceled = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def cancel(self, user):
        self.date_canceled = now()
        self.canceled_by = user
        self.save()

    def update(self, user):
        self.date_updated = now()
        self.updated_by = user
        self.save()


# Modelos de pessoas, contatos e endereços
class City(BaseModel):
    code = models.CharField(max_length=255)
    name = models.CharField(max_length=255, db_index=True)
    uf = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "city"
        indexes = [
            models.Index(fields=["name"]),
        ]


class PersonType(BaseModel):
    type = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "person_type"

    def __str__(self):
        return self.type


class Person(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    cpf = models.CharField(max_length=20, unique=True, null=True, blank=True)
    person_type = models.ForeignKey(PersonType, on_delete=models.CASCADE)
    is_infant = models.BooleanField(default=False)

    class Meta:
        db_table = "person"

    def __str__(self):
        return f"{self.name}"


class PersonsContacts(BaseModel):
    phone = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)  # Removido unique para permitir compartilhamento
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="contacts"
    )

    class Meta:
        db_table = "persons_contacts"

    def __str__(self):
        return f"({self.person.name}) - email: {self.email} - phone: {self.phone}"


class PersonsAdresses(BaseModel):
    street = models.CharField(max_length=255, null=True, blank=True)
    number = models.CharField(max_length=255, null=True, blank=True)
    cep = models.CharField(max_length=255, null=True, blank=True)
    neighborhood = models.CharField(max_length=255, null=True, blank=True)
    complemento = models.CharField(max_length=255, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    class Meta:
        db_table = "persons_adresses"

    def __str__(self):
        return f"({self.person.name}) - address: {self.street} - neighborhood: {self.neighborhood}"
